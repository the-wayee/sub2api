"""Small authenticated subscription editor for a JSON-format Mihomo config."""
import copy
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).parent
CONFIG = Path(os.environ.get("MIHOMO_CONFIG", "/home/ubuntu/mihomo-deploy/config.yaml"))
CONTAINER = "mihomo-mihomo-1"
ORIGIN = "https://proxy.opentv.fans"
TOKEN = os.environ.get("SUBSCRIPTION_TOKEN", "")
LOCK = threading.Lock()


def validate_url(url):
    if len(url) > 4096:
        raise ValueError("订阅链接过长")
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError("请填写完整的 HTTPS 订阅链接")
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError):
        raise ValueError("订阅域名无法解析，请检查链接") from None
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("订阅链接必须使用公网地址")


def edit_config(config, action, body):
    result = copy.deepcopy(config)
    providers = result.setdefault("proxy-providers", {})
    original = str(body.get("original", ""))
    name = str(body.get("name", "")).strip()
    if action == "delete":
        if original not in providers:
            raise ValueError("订阅已不存在，请刷新页面")
        if len(providers) <= 1:
            raise ValueError("请至少保留一个订阅，以免中断代理服务")
        del providers[original]
        for group in result.get("proxy-groups", []):
            group["use"] = [n for n in group.get("use", []) if n != original]
            if not group["use"] and not group.get("proxies"):
                raise ValueError("删除后有代理分组没有可用节点，请先调整分组")
        return result
    if not re.fullmatch(r"[\w\- ]{1,40}", name) or name in {"GLOBAL", "DIRECT", "REJECT"}:
        raise ValueError("名称请使用 1–40 个字母、数字、中文、空格或短横线")
    if name in {g.get("name") for g in result.get("proxy-groups", [])}:
        raise ValueError("订阅名称不能与代理分组重名")
    if original and original not in providers:
        raise ValueError("订阅已不存在，请刷新页面")
    if name in providers and name != original:
        raise ValueError("已有同名订阅")
    url = str(body.get("url", "")).strip()
    if not url and original:
        url = providers[original].get("url", "")
    validate_url(url)
    try:
        interval = int(body.get("interval", 86400))
    except (TypeError, ValueError):
        raise ValueError("更新周期必须是整数") from None
    if interval < 3600 or interval > 604800:
        raise ValueError("更新周期应为 1 小时到 7 天")
    provider = copy.deepcopy(providers[original]) if original else {
        "type": "http", "path": "./providers/managed-" + secrets.token_hex(8) + ".yaml",
        "header": {"User-Agent": ["Clash.Meta"]},
        "health-check": {"enable": True, "url": "https://www.gstatic.com/generate_204", "interval": 300},
        "override": {"additional-prefix": "[" + name + "] "},
    }
    if provider.get("type") != "http":
        raise ValueError("此页面仅管理 HTTP 订阅")
    provider.update(url=url, interval=interval)
    if original and name != original:
        del providers[original]
        if "override" in provider and "additional-prefix" in provider["override"]:
            provider["override"]["additional-prefix"] = "[" + name + "] "
    providers[name] = provider
    found = False
    for group in result.get("proxy-groups", []):
        if original:
            group["use"] = [name if n == original else n for n in group.get("use", [])]
        if group.get("name") == "AI-PROXY":
            found = True
            if name not in group.setdefault("use", []):
                group["use"].append(name)
    if not found:
        raise ValueError("未找到 AI-PROXY 分组")
    return result


def core_request(config, path, method="GET", body=None):
    ip = subprocess.check_output(["docker", "inspect", CONTAINER, "--format",
                                  '{{(index .NetworkSettings.Networks "sub2api-proxy").IPAddress}}'],
                                 text=True, timeout=10).strip()
    if not ipaddress.ip_address(ip).is_private:
        raise RuntimeError("Unexpected controller address")
    request = Request("http://" + ip + ":9090" + path, method=method,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={"Authorization": "Bearer " + config["secret"], "Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=45) as response:
        data = response.read()
        return json.loads(data) if data else {}


def apply_config(old, new):
    payload = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
    # Validate without starting a second core or interpolating user values into shell commands.
    process = subprocess.run(["docker", "exec", "-i", CONTAINER, "sh", "-c",
                              "umask 077; cat > /root/.config/mihomo/.subscription-check.json; "
                              "/mihomo -t -f /root/.config/mihomo/.subscription-check.json "
                              "-d /root/.config/mihomo >/dev/null 2>&1; "
                              "result=$?; rm -f /root/.config/mihomo/.subscription-check.json; exit $result"],
                             input=payload, text=True, capture_output=True, timeout=60)
    if process.returncode:
        raise ValueError("Mihomo 配置校验失败，原配置未修改")
    backup = CONFIG.parent / "subscription-backups"
    backup.mkdir(mode=0o700, exist_ok=True)
    filename = backup / (str(time.time_ns()) + ".json")
    filename.write_bytes(CONFIG.read_bytes())
    filename.chmod(0o600)
    # Keep the inode: config.yaml is a Docker file bind mount.
    try:
        CONFIG.write_text(payload)
        core_request(new, "/configs?force=true", "PUT", {"path": "/root/.config/mihomo/config.yaml"})
    except Exception:
        CONFIG.write_bytes(filename.read_bytes())
        try:
            core_request(old, "/configs?force=true", "PUT", {"path": "/root/.config/mihomo/config.yaml"})
        except Exception:
            raise RuntimeError("保存失败，已恢复配置文件；核心重载失败，请联系管理员") from None
        raise RuntimeError("保存失败，已恢复原配置和核心") from None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log subscription URLs or authentication values.

    def respond(self, status, data, content_type="application/json; charset=utf-8"):
        raw = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        return bool(TOKEN) and hmac.compare_digest(self.headers.get("X-Subscription-Token", "").encode(), TOKEN.encode())

    def do_GET(self):
        if not self.authorized():
            return self.respond(403, {"error": "需要通过代理管理域名登录"})
        path = urlsplit(self.path).path
        files = {"/subscriptions/": ("index.html", "text/html; charset=utf-8"),
                 "/subscriptions/app.js": ("app.js", "text/javascript; charset=utf-8"),
                 "/subscriptions/style.css": ("style.css", "text/css; charset=utf-8")}
        if path in files:
            filename, kind = files[path]
            return self.respond(200, (ROOT / filename).read_bytes(), kind)
        if path != "/subscriptions/api":
            return self.respond(404, {"error": "页面不存在"})
        with LOCK:
            try:
                config = json.loads(CONFIG.read_text())
                runtime = {}
                try:
                    runtime = core_request(config, "/providers/proxies").get("providers", {})
                except Exception:
                    pass
                rows = []
                for name, p in config.get("proxy-providers", {}).items():
                    if p.get("type") != "http":
                        continue
                    state = runtime.get(name, {})
                    rows.append({"name": name, "host": urlsplit(p.get("url", "")).hostname,
                                 "interval": p.get("interval", 86400), "nodes": len(state.get("proxies", [])),
                                 "updated": state.get("updatedAt", ""),
                                 "active": any(name in g.get("use", []) for g in config.get("proxy-groups", []) if g.get("name") == "AI-PROXY")})
                return self.respond(200, {"subscriptions": rows})
            except Exception:
                return self.respond(500, {"error": "读取订阅失败，请联系管理员"})

    def do_POST(self):
        if not self.authorized():
            return self.respond(403, {"error": "需要登录"})
        if self.headers.get("Origin") != ORIGIN or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.respond(403, {"error": "请从订阅管理页面操作"})
        if self.path != "/subscriptions/api":
            return self.respond(404, {"error": "页面不存在"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 16384:
                raise ValueError("请求长度无效")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("请求格式无效")
            action = body.get("action")
            if action not in {"save", "delete", "refresh"}:
                raise ValueError("操作无效")
            with LOCK:
                config = json.loads(CONFIG.read_text())
                if action == "refresh":
                    name = str(body.get("original", ""))
                    if name not in config.get("proxy-providers", {}):
                        raise ValueError("订阅不存在")
                    from urllib.parse import quote
                    core_request(config, "/providers/proxies/" + quote(name, safe=""), "PUT")
                else:
                    apply_config(config, edit_config(config, action, body))
            return self.respond(200, {"ok": True})
        except ValueError as error:
            return self.respond(400, {"error": str(error)})
        except Exception:
            return self.respond(500, {"error": "操作失败，未确认生效。请刷新查看；若保存失败，系统会尝试恢复原配置。"})


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("SUBSCRIPTION_TOKEN is required")
    ThreadingHTTPServer((os.environ.get("LISTEN_HOST", "172.20.0.1"), 9071), Handler).serve_forever()
