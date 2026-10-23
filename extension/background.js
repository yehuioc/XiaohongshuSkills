importScripts('executor.js');
const BASE = 'http://127.0.0.1:8914', ALARM = 'xhs-runner-reconnect';
const panels = new Set();
let token = '', binding = null, active = null, timer = null, ticking = false, initialized;
let message = '请先从工作台取得配对码。', connected = false, writes = Promise.resolve(), lastTick = 0;
const executor = createXhsExecutor({getBinding: () => binding, getJob: () => active, stop, post});
chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true});

function state() { return {paired: !!token, binding: binding ? {...binding} : null, busy: !!active, connected, message, version: chrome.runtime.getManifest().version}; }
function broadcast() { for (const port of panels) { try { port.postMessage(state()); } catch (_) { panels.delete(port); } } }
function persist() {
  const value = {binding: binding ? {...binding} : null, flight: active ? {id: active.id, session: active.session, remote: active.remote} : null, message};
  writes = writes.catch(() => {}).then(() => chrome.storage.session.set({runnerState: value}));
  return writes;
}
async function post(path, body) {
  const response = await fetch(BASE + path, {method: 'POST', headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + token}, body: JSON.stringify(body), signal: AbortSignal.timeout(8000)});
  const result = await response.json(); if (!response.ok) throw Error(result.error || '本地连接失败'); return result.result;
}
async function init() {
  if (initialized) return initialized;
  initialized = (async () => {
    token = (await chrome.storage.local.get('token')).token || '';
    const saved = await chrome.storage.session.get(['runnerState', 'lastBinding']);
    binding = saved.runnerState ? saved.runnerState.binding : (saved.lastBinding ? {...saved.lastBinding, control: false, grant_at: 0, session: crypto.randomUUID()} : null);
    if (binding) {
      binding.instance ||= crypto.randomUUID(); binding.revision ||= 1; binding.runner = 'background';
      binding.version = chrome.runtime.getManifest().version;
      message = saved.runnerState?.message || '已恢复绑定，AI 接管尚未开启。';
      if (saved.runnerState?.flight) {
        const flight = saved.runnerState.flight;
        stop('扩展执行器曾中断，未重放未完成操作。请检查页面后重新开启接管。');
        if (flight.remote) post('/bridge/result', {...flight, error: '扩展执行器中断，未自动重放'}).catch(() => {});
      }
      try {
        await executor.check(binding.session);
        const account = await executor.site('identity');
        if (!account.user_id || account.user_id !== binding.account_id) stop('账号改变或无法核对，请重新绑定');
      } catch (e) { stop(e.message); }
      await persist(); await alarm();
    } else message = token ? '已记住配对，请绑定需要使用的小红书页面。' : message;
    schedule(0); return state();
  })();
  return initialized;
}
function schedule(ms = 1500) {
  clearTimeout(timer);
  if (binding && token && (binding.control || panels.size)) timer = setTimeout(tick, ms);
}
async function alarm() {
  if (binding?.control) await chrome.alarms.create(ALARM, {periodInMinutes: 1});
  else await chrome.alarms.clear(ALARM);
}
async function markPage() {
  if (!binding) return;
  const b = {...binding}, issuedAt = Date.now();
  await chrome.scripting.executeScript({target: {tabId: b.tab_id}, world: 'ISOLATED', func: (enabled, revision, instance, issuedAt) => {
    let box = document.getElementById('xhs-research-workbench-marker');
    if (box && (Number(box.dataset.issuedAt || 0) > issuedAt || (box.dataset.instance === instance && Number(box.dataset.revision) > revision))) return;
    if (!box) { box = document.createElement('div'); box.id = 'xhs-research-workbench-marker'; document.documentElement.append(box); }
    box.dataset.revision = String(revision);
    box.dataset.instance = instance; box.dataset.issuedAt = String(issuedAt);
    box.textContent = enabled ? '此页已绑定研究工作台 · AI 可在后台操作 · 可在工作台停止' : '此页已绑定研究工作台 · 当前由你操作';
    box.style.cssText = 'position:fixed;bottom:18px;left:18px;z-index:2147483647;padding:10px 16px;border-radius:8px;background:' + (enabled ? '#244e3b' : '#555') + ';color:white;font:14px system-ui;box-shadow:0 2px 15px #0003;pointer-events:none';
  }, args: [b.control, b.revision, b.instance, issuedAt]});
}
function cancelPage(job) {
  if (!job) return;
  chrome.scripting.executeScript({target: {tabId: job.tab_id}, world: 'MAIN', func: id => {
    const run = window.__xhsResearchActions?.[id]; if (run) run.abort.abort();
  }, args: [job.id]}).catch(() => {});
}
async function restoreDiscardability(tabId, original) {
  if (typeof original !== 'boolean') return;
  await chrome.tabs.update(tabId, {autoDiscardable: original});
  // A new user grant may have overtaken this asynchronous restoration.
  if (binding?.tab_id === tabId && binding.control) await chrome.tabs.update(tabId, {autoDiscardable: false});
}
function stop(reason = '已交还给你，AI 操作已停止。') {
  if (active) { active.cancelled = true; active.abort.abort(); cancelPage(active); }
  if (binding) {
    const tabId = binding.tab_id, original = binding.auto_discardable;
    binding.control = false; binding.grant_at = 0; binding.session = crypto.randomUUID(); binding.revision++;
    restoreDiscardability(tabId, original).catch(() => {});
  }
  message = reason; persist(); alarm().catch(() => {}); broadcast();
  if (token && binding) post('/bridge/poll', {binding: {...binding}, busy: !!active, status: message})
    .then(() => {connected = true;}, () => {connected = false;}).finally(broadcast);
  markPage().catch(() => {}); schedule(0);
}
async function tick() {
  if (ticking) return; ticking = true;
  try {
    if (!binding || !token) return;
    if (binding.control && lastTick && Date.now() - lastTick > 20000) stop('浏览器运行曾中断或电脑休眠，已暂停；请核对页面后重新开启接管。');
    lastTick = Date.now();
    // A real tabs API observation resets Chrome 110+'s worker idle timer.
    // The loop lives here, never in a hidden panel or the target page.
    try { await executor.check(binding.session); } catch (e) { if (binding.control) stop(e.message); }
    const sent = {...binding};
    const command = await post('/bridge/poll', {binding: sent, busy: !!active, executing: active?.remote && !active.reporting ? {id: active.id, session: active.session} : null, status: message});
    connected = true;
    if (!binding || sent.session !== binding.session) return;
    if (command?.stop) stop('工作台已停止接管。需要继续时请主动开启。');
    else if (command?.cancel && active?.id === command.cancel && !active.reporting) stop('当前操作已取消或过期，未继续执行。');
    else if (command?.id && !active) {
      if (!binding.control || command.session !== binding.session) return;
      if (Date.now() / 1000 >= command.expires) throw Error('收到过期操作，未执行');
      // Do not await: heartbeats and stop delivery continue during uploads/downloads.
      runJob(command, true).catch(() => {}); // runJob already records the useful stop reason.
    }
  } catch (e) {
    connected = false;
    if (binding?.control) stop('本机连接中断，已暂停接管：' + e.message);
    else message = '本机连接未就绪：' + e.message;
  } finally { ticking = false; broadcast(); schedule(); }
}
async function runJob(command, remote, task) {
  if (active) throw Error('当前页正在执行操作，请先停止或等待完成');
  const job = {...command, remote, tab_id: binding.tab_id, cancelled: false, abort: new AbortController()};
  active = job; message = '正在操作已绑定页面；可以切换标签页或关闭侧栏。'; broadcast();
  let result, error;
  try {
    await persist();
    if (job.cancelled) throw Error('操作已停止');
    result = await (task ? task() : executor.execute(command.action, command.args, true));
    if (job.cancelled || binding?.session !== command.session) throw Error('操作已停止，结果未接入');
    message = '操作完成，可以继续使用其他标签页。';
  } catch (e) {
    error = e.message;
    if (!job.cancelled && !e.recoverable) stop('操作未完成，已停止接管：' + error);
    else if (!job.cancelled) message='本次操作已停下，请核对页面后重试：'+error;
  } finally {
    if (remote) {
      job.reporting = true;
      try { await post('/bridge/result', {id: command.id, session: command.session, result: error ? null : result, error}); }
      catch (e) { if (!job.cancelled) {message = '结果未接入：' + e.message; if (binding?.control) stop(message);} }
    }
    active = null; await persist(); broadcast(); schedule(0);
  }
  if (error) throw Error(error); return result;
}
function manual(task) { return runJob({id: crypto.randomUUID(), session: binding?.session, expires: Date.now() / 1000 + 40}, false, task); }
async function handle(action, args = {}) {
  await init();
  if (action === 'state') return state();
  if (action === 'stop') {
    stop(); await persist();
    if (token && binding) await post('/bridge/poll', {binding: {...binding}, busy: !!active}).catch(() => {});
    return state();
  }
  if (action === 'pair') {
    if (active) throw Error('请先停止当前操作');
    if (binding) {stop(); if (token) await post('/bridge/poll', {binding: {...binding}});}
    const result = await post('/bridge/pair', {code: String(args.code || '').trim().toUpperCase()});
    token = result.token; await chrome.storage.local.set({token});
    message = '已配对，请绑定需要使用的小红书页面。'; schedule(0); broadcast(); return state();
  }
  if (action === 'bind') {
    if (active) throw Error('请先停止并等待当前操作结束，再绑定其他页面');
    stop(); const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (!/^https:\/\/(?:www|creator)\.xiaohongshu\.com\//.test(tab?.url || '')) throw Error('请先选中小红书页面，再点击绑定');
    const revision = (binding?.revision || 0) + 1;
    binding = {tab_id: tab.id, instance: binding?.instance || crypto.randomUUID(), revision, runner: 'background', version: chrome.runtime.getManifest().version, grant_at: 0,
      session: crypto.randomUUID(), control: false, url: tab.url.split('?')[0], title: pageTitle(tab), account_id: '', auto_discardable: tab.autoDiscardable};
    const user = await executor.site('identity');
    if (!user.user_id) { binding = null; await persist(); throw Error('未能确认登录账号，请先正常登录'); }
    binding.account_id = user.user_id; message = '已绑定。可以手动收集，需要 AI 操作时请开启接管。';
    await persist(); await markPage(); schedule(0); broadcast(); return state();
  }
  if (!binding) throw Error('请先绑定标签页');
  if (action === 'control') {
    if (!args.enabled) return handle('stop');
    if (active) throw Error('当前页正在操作，请等待完成');
    const session = binding.session, user = await executor.site('identity');
    await executor.check(session);
    if (user.user_id !== binding.account_id || !user.user_id) {stop('账号改变，请重新绑定'); throw Error('账号改变，请重新绑定');}
    binding.control = true; binding.grant_at = Date.now() / 1000; binding.session = crypto.randomUUID(); binding.revision++;
    lastTick = Date.now();
    const enabledSession = binding.session, tabId = binding.tab_id, original = binding.auto_discardable;
    try {await chrome.tabs.update(tabId, {autoDiscardable: false});}
    catch(e) {stop('标签页状态无法确认，未开启接管'); throw e;}
    if (!binding.control || binding.session !== enabledSession) {await restoreDiscardability(tabId, original); throw Error('接管已停止');}
    message = '后台接管已开启。切换标签页、最小化或关闭侧栏均可继续；点击停止才交还控制。';
    await persist(); await alarm(); await markPage(); schedule(0); broadcast(); return state();
  }
  if (action === 'focus') {
    const tab = await chrome.tabs.get(binding.tab_id);
    await chrome.tabs.update(tab.id, {active: true}); await chrome.windows.update(tab.windowId, {focused: true});
    await markPage(); return state();
  }
  if (action === 'open_editor') {
    if (active) throw Error('请先停止并等待当前操作结束');
    await manual(() => executor.execute('open_editor', {}, binding.control));
    message = binding.control ? '已核对同一账号并打开创作者编辑器，接管继续有效；现有草稿保留。' : '已打开创作者编辑器，仍由你操作。';
    await persist(); broadcast(); return state();
  }
  if (action === 'list') return manual(() => executor.execute('snapshot'));
  if (action === 'open_note') return manual(() => executor.execute('open_note', {note_id: args.note_id}));
  if (action === 'capture') return manual(async () => {
    const tab = await executor.check(binding.session), id = tab.url.match(/\/(?:explore|search_result)\/([a-f0-9]{24})/)?.[1];
    if (!id) throw Error('请先打开一篇笔记详情');
    return post('/bridge/capture', await executor.execute('read_note', {note_id: id}));
  });
  throw Error('未开放此扩展动作');
}
chrome.runtime.onMessage.addListener((request, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.url !== chrome.runtime.getURL('panel.html')) return false;
  handle(request.action, request.args).then(result => reply({result}), error => reply({error: error.message})); return true;
});
chrome.runtime.onConnect.addListener(port => {
  if (port.name !== 'xhs-panel' || port.sender?.id !== chrome.runtime.id || port.sender?.url !== chrome.runtime.getURL('panel.html')) return port.disconnect();
  panels.add(port); port.onDisconnect.addListener(() => {panels.delete(port); schedule();});
  init().then(() => {broadcast(); schedule(0);});
});
chrome.alarms.onAlarm.addListener(event => {if (event.name === ALARM) init().then(() => {alarm(); schedule(0);});});
chrome.runtime.onStartup.addListener(() => init());
chrome.runtime.onInstalled.addListener(() => init());
chrome.tabs.onRemoved.addListener(id => {init().then(() => {if (binding?.tab_id === id) {stop('绑定标签页已关闭，请重新绑定'); binding = null; persist(); broadcast();}});});
chrome.tabs.onUpdated.addListener((id, change, tab) => {init().then(() => {
  if (binding?.tab_id !== id) return;
  if ((change.url && !/^https:\/\/(?:www|creator)\.xiaohongshu\.com\//.test(change.url)) || change.discarded || change.frozen) {
    stop('绑定页已离开小红书、被冻结或释放，请检查页面后重新开启接管'); return;
  }
  if (tab?.url) {binding.url = tab.url.split('?')[0]; binding.title = pageTitle(tab); broadcast();}
  if (change.status === 'complete') markPage().catch(() => {});
});});
