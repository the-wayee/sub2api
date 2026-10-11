"""Install routes on the existing OpenTV host. Run with sudo, after copying service files."""
from pathlib import Path
import secrets
import shutil
import time
import pwd
import os
import hashlib
import re

root=Path('/home/ubuntu/mihomo-deploy')
env=root/'subscription-manager.env'
if not env.exists():
    env.write_text('SUBSCRIPTION_TOKEN='+secrets.token_urlsafe(48)+'\n')
    env.chmod(0o600)
token=env.read_text().strip().split('=',1)[1]
caddy=Path('/opt/opentv/docker/Caddyfile')
text=caddy.read_text()
backup=root/'subscription-backups'/('install-'+str(time.time_ns()))
backup.mkdir(parents=True,mode=0o700)
account=pwd.getpwnam('ubuntu')
os.chown(backup.parent,account.pw_uid,account.pw_gid)
shutil.copy2(caddy,backup/'Caddyfile')
index=root/'panel-static/index.html'
shutil.copy2(index,backup/'index.html')
shutil.copy2(root/'config.yaml',backup/'config.yaml')
if '/subscriptions/*' not in text:
    target='        reverse_proxy opentv-proxy-panel:80'
    if text.count(target)!=1: raise SystemExit('Panel route not found or ambiguous')
    text=text.replace(target,'''        redir /subscriptions /subscriptions/ 308
        handle /subscriptions/* {
            reverse_proxy 172.20.0.1:9071 {
                header_up X-Subscription-Token "'''+token+'''"
            }
        }
        handle {
            reverse_proxy opentv-proxy-panel:80
        }''')
if '# opentv-subscription-login-help' not in text:
    site='proxy.opentv.fans {'
    if text.count(site)!=1: raise SystemExit('Proxy site not found or ambiguous')
    text=text.replace(site, site+'''
    # opentv-subscription-login-help
    handle_errors {
        @loginRequired expression {err.status_code} == 401
        header @loginRequired Content-Type "text/html; charset=utf-8"
        header @loginRequired Cache-Control "no-store"
        respond @loginRequired `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>需要登录 · OpenTV Proxy</title><body style="font-family:system-ui;background:#f4f7fb;color:#172033;padding:60px 24px"><main style="max-width:560px;margin:auto;background:white;padding:32px;border-radius:16px"><h1>请先登录代理管理面板</h1><p>这个页面需要原代理面板的账号密码，用户名为 admin。</p><p>浏览器没有弹出登录窗口时，请打开无痕窗口，访问下面的地址，再输入原面板密码。</p><p><a href="https://proxy.opentv.fans/subscriptions/">https://proxy.opentv.fans/subscriptions/</a></p><p>Chrome 无痕窗口快捷键：Mac 按 ⌘ + Shift + N；Windows 按 Ctrl + Shift + N。</p></main></body></html>` 401
    }
''')
caddy.write_text(text)
sw=root/'panel-static/sw.js'
if sw.exists() and 'opentv-subscriptions-network-only' not in sw.read_text():
    worker=sw.read_text()
    navigation='new n.NavigationRoute(n.createHandlerBoundToURL("./"))'
    if navigation not in worker: raise SystemExit('Unexpected panel navigation worker; review before patching')
    shutil.copy2(sw,backup/'sw.js')
    worker=worker.replace(navigation,'new n.NavigationRoute(n.createHandlerBoundToURL("./"),{denylist:[/^\\/subscriptions(?:\\/|$)/]})')
    bootstrap='''// opentv-subscriptions-network-only
self.addEventListener("install",event=>event.waitUntil(self.skipWaiting()));
self.addEventListener("activate",event=>event.waitUntil((async()=>{
    await self.clients.claim();
    for (const client of await self.clients.matchAll({type:"window"})) {
        if (/^\\/subscriptions(?:\\/|$)/.test(new URL(client.url).pathname)) await client.navigate(client.url);
    }
})()));
'''
    sw.write_text(bootstrap+worker)
html=index.read_text()
if 'opentv-subscription-link' not in html:
    link='<a id="opentv-subscription-link" href="/subscriptions/" style="position:fixed;bottom:24px;right:24px;z-index:9999;background:#2563eb;color:white;padding:12px 18px;border-radius:12px;text-decoration:none;font:600 14px system-ui;box-shadow:0 4px 20px #0004">＋ 管理订阅</a>'
    if '</body>' not in html: raise SystemExit('Panel body not found')
    index.write_text(html.replace('</body>',link+'</body>'))
if sw.exists():
    # Updating the worker alone does not invalidate Workbox's cached panel HTML.
    revision=hashlib.sha256(index.read_bytes()).hexdigest()
    worker=sw.read_text()
    worker=re.sub(r'(url:"\./",revision:")[^"]+("})',lambda match:match[1]+revision+match[2],worker)
    sw.write_text(worker)
print('Routes and panel entry installed. Backup:',backup)
