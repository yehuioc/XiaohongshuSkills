// The panel only displays and controls the independent background runner.
const el = id => document.getElementById(id);
let view = null;
async function call(action, args = {}) {
  const response = await chrome.runtime.sendMessage({action, args});
  if (!response || response.error) throw Error(response?.error || '扩展后台未响应，请重新打开侧栏');
  return response.result;
}
function render(value) {
  view = value; const b = value.binding;
  el('binding').textContent = b ? '外部 Chrome · ' + (b.title || '小红书') + '\n' + b.url + '\n' + (b.control ? '后台接管已开启 · 关闭侧栏仍继续' : '由你操作 · AI 接管已关闭') : '尚未绑定，工作台所在的内置浏览器不会被控制。';
  el('control').checked = !!b?.control; el('control').disabled = !b;
  el('focus').disabled = !b; el('open-editor').disabled = !b || value.busy;
  el('bind').disabled = value.busy; el('capture').disabled = !b || value.busy; el('list').disabled = !b || value.busy;
  el('status').textContent = value.message;
  el('version').textContent = '扩展 ' + value.version + ' · 后台执行器 · ' + (value.connected ? '工作台已连接' : '工作台连接待确认');
}
function action(id, fn) {el(id).onclick = async () => {try {await fn();} catch (e) {el('status').textContent = e.message;}};}
action('pair', async () => {render(await call('pair', {code: el('code').value})); el('code').value = '';});
action('bind', async () => render(await call('bind')));
action('stop', async () => render(await call('stop')));
action('focus', async () => render(await call('focus')));
action('open-editor', async () => render(await call('open_editor')));
el('control').onchange = async () => {try {render(await call('control', {enabled: el('control').checked}));} catch (e) {el('control').checked = !!view?.binding?.control; el('status').textContent = e.message;}};
action('capture', async () => {const result = await call('capture'); el('status').textContent = '已保存到工作台，实际图片 ' + result.coverage.images_available + ' 张。';});
action('list', async () => {
  const result = await call('list'); const area = el('cards'); area.replaceChildren();
  for (const card of result.cards) {const button = document.createElement('button'); button.textContent = card.title;
    button.onclick = async () => {try {await call('open_note', {note_id: card.note_id}); el('status').textContent = '已打开，可收集当前笔记。';} catch (e) {el('status').textContent = e.message;}}; area.append(button);}
  el('status').textContent = result.scope;
});
const port = chrome.runtime.connect({name: 'xhs-panel'});
port.onMessage.addListener(render);
port.onDisconnect.addListener(() => {el('status').textContent = '扩展后台已重载，请重新打开侧栏。';});
call('state').then(render, e => {el('status').textContent = e.message;});
