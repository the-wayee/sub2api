# OpenTV 代理订阅管理

独立的 Python 标准库服务，与 MetaCubeXD 共用 `proxy.opentv.fans` 的现有 Basic Auth。页面入口 `/subscriptions/`，原面板右下角提供“管理订阅”链接。支持新增、编辑、更新和删除 HTTP 订阅，新增订阅自动加入 `AI-PROXY`。删除最后一个订阅会被阻止。

## 部署环境

适用于当前服务器布局：`/home/ubuntu/mihomo-deploy/config.yaml` 为 JSON 格式的 Mihomo 配置，核心容器 `mihomo-mihomo-1`，网络 `sub2api-proxy` 的宿主地址 `172.20.0.1`，外部 Caddy 配置 `/opt/opentv/docker/Caddyfile`，静态面板 `panel-static/index.html`。

把 `server.py`、`index.html`、`app.js`、`style.css`、`install_routes.py` 和 service 文件复制到 `~/mihomo-deploy/subscription-manager/`，执行：

```bash
sudo python3 ~/mihomo-deploy/subscription-manager/install_routes.py
sudo cp ~/mihomo-deploy/subscription-manager/opentv-subscriptions.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now opentv-subscriptions
docker exec opentv-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec opentv-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

安装脚本保留原配置与面板备份，生成服务器内部认证令牌；不要提交 `subscription-manager.env`。验证 Caddy 配置成功后再重载。更新应用文件后执行 `sudo systemctl restart opentv-subscriptions`。重建或更新 MetaCubeXD 静态文件后，再运行安装脚本恢复入口。

## 保存与恢复

保存时先在核心容器内运行 Mihomo 配置校验；通过后备份原文件，原地写入以保留 Docker 文件挂载，再调用控制器热重载。重载失败时恢复配置与核心。备份位于 `subscription-backups/`；包含敏感信息，只能由管理员访问。

UI 不返回完整订阅 URL 或控制器密钥，编辑 URL 留空时保留原地址。所有请求需要 Caddy 注入内部令牌，写操作还要求同源 Origin。仅支持 HTTPS 公网订阅地址。新订阅节点名会加订阅名称前缀，避免多个订阅的节点名称冲突。此服务专用于管理员，未实现普通用户的订阅隔离。

## 验证

```bash
python3 -m unittest discover -s deploy/proxy-subscriptions -p 'test_*.py'
node --check deploy/proxy-subscriptions/app.js
```

测试覆盖新增、重命名、删除、保留原配置、拒绝内网地址、禁止删除最后一个订阅和保存失败回滚。

## MetaCubeXD 离线缓存兼容

安装脚本会给原面板 `sw.js` 的导航回退添加 `/subscriptions` 排除规则，避免将订阅页替换成缓存的 Nuxt 首页。新版 worker 立即接管，并重新加载已经打开的订阅页；同时更新面板首页的预缓存版本，确保“管理订阅”入口可见。已打开旧面板的浏览器需刷新原面板以触发 worker 更新。未登录的 401 返回明确的登录说明。
