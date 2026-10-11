const $ = (id) => document.getElementById(id);
let editing = '', deleting = '', pending = false;
function message(text, error = false) { $('message').textContent = text; $('message').className = error ? 'error' : ''; $('message').hidden = false; }
async function api(body) {
  const response = await fetch('/subscriptions/api', body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作失败');
  return data;
}
function node(tag, cls, text) { const n = document.createElement(tag); n.className = cls; n.textContent = text; return n; }
function button(text, cls, action) { const b = node('button', cls, text); b.onclick = action; return b; }
async function load() {
  $('reload').disabled = true;
  try {
    const {subscriptions} = await api();
    $('count').textContent = subscriptions.length;
    $('nodes').textContent = subscriptions.reduce((n, p) => n + p.nodes, 0);
    $('list').replaceChildren();
    for (const row of subscriptions) {
      const card = node('article', 'card', ''); const head = node('div', 'card-head', '');
      head.append(node('h2', '', row.name), node('span', 'pill', row.active ? '已接入 AI-PROXY' : '未接入分组'));
      card.append(head, node('p', 'domain', row.host || '订阅地址已隐藏'));
      const meta = node('div', 'meta', ''); meta.append(node('span', '', `${row.nodes} 个节点`), node('span', '', `每 ${Math.round(row.interval / 3600)} 小时更新`)); card.append(meta);
      const date = new Date(row.updated); card.append(node('p', 'updated', row.updated && !isNaN(date) ? `最近更新：${date.toLocaleString('zh-CN')}` : '尚未获取节点，尝试更新订阅'));
      const actions = node('div', 'card-actions', '');
      const refresh = button('更新订阅', 'quiet', async () => { refresh.disabled = true; try { await api({action:'refresh',original:row.name}); message('订阅已更新'); await load(); } catch(e) { message(e.message,true); } finally { refresh.disabled=false; } });
      actions.append(refresh, button('编辑', 'quiet', () => openEditor(row)), button('删除', 'danger', () => { deleting=row.name; $('delete-text').textContent=`确认删除「${row.name}」？`; $('delete-error').textContent=''; $('delete-dialog').showModal(); }));
      card.append(actions); $('list').append(card);
    }
    if (!subscriptions.length) $('list').append(node('p','empty','还没有订阅，点击“新增订阅”开始。'));
  } catch(e) { message(e.message,true); } finally { $('reload').disabled=false; }
}
function openEditor(row) {
  editing = row?.name || ''; $('title').textContent = row ? '编辑订阅' : '新增订阅';
  $('name').value=editing; $('url').value=''; $('url').required=!row;
  $('interval').value=String(row?.interval || 86400);
  if (!$('interval').value) { const o=node('option','',`每 ${row.interval / 3600} 小时`); o.value=row.interval; $('interval').append(o); $('interval').value=String(row.interval); }
  $('url-help').textContent=row ? '链接留空保留原地址；填写新链接可替换订阅。' : '使用服务商提供的 Clash / Mihomo 订阅链接。';
  $('form-error').textContent=''; $('editor').showModal();
}
$('add').onclick=()=>openEditor(); $('reload').onclick=load;
$('close').onclick=$('cancel').onclick=()=>{if(!pending) $('editor').close();};
$('editor').addEventListener('cancel',e=>{if(pending)e.preventDefault();});
$('form').onsubmit=async(e)=>{
  e.preventDefault(); if(pending)return; pending=true; $('save').disabled=true; $('save').textContent='正在校验并应用…';
  try { await api({action:'save',original:editing,name:$('name').value,url:$('url').value,interval:Number($('interval').value)}); $('editor').close(); message('订阅已保存并应用。可前往节点面板切换节点。'); await load(); }
  catch(e){$('form-error').textContent=e.message;} finally{pending=false;$('save').disabled=false;$('save').textContent='保存并应用';}
};
$('delete-cancel').onclick=()=>{if(!pending)$('delete-dialog').close();};
$('delete-dialog').addEventListener('cancel',e=>{if(pending)e.preventDefault();});
$('delete-confirm').onclick=async()=>{
  if(pending)return;pending=true;$('delete-confirm').disabled=true;
  try {await api({action:'delete',original:deleting});$('delete-dialog').close();message('订阅已删除，配置备份已保留。');await load();}
  catch(e){$('delete-error').textContent=e.message;}finally{pending=false;$('delete-confirm').disabled=false;}
};
load();
