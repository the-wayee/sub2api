"""Install routes on the existing OpenTV host. Run with sudo, after copying service files."""
from pathlib import Path
import secrets
import shutil
import time
import pwd
import os

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
    caddy.write_text(text)
html=index.read_text()
if 'opentv-subscription-link' not in html:
    link='<a id="opentv-subscription-link" href="/subscriptions/" style="position:fixed;bottom:24px;right:24px;z-index:9999;background:#2563eb;color:white;padding:12px 18px;border-radius:12px;text-decoration:none;font:600 14px system-ui;box-shadow:0 4px 20px #0004">＋ 管理订阅</a>'
    if '</body>' not in html: raise SystemExit('Panel body not found')
    index.write_text(html.replace('</body>',link+'</body>'))
print('Routes and panel entry installed. Backup:',backup)
