// One fixed-site executor, owned by the service worker. No UI or foreground dependency.
function createXhsExecutor({getBinding, stop, post, getJob}) {
  const allowed = url => /^https:\/\/(?:www|creator)\.xiaohongshu\.com\//.test(url || '');
  async function check(session, controlled = false) {
    const valid = () => {
      const b = getBinding();
      if (!b || b.session !== session || (controlled && !b.control) || getJob()?.cancelled) throw Error('接管已停止或标签页重新绑定');
      return b;
    };
    const b = valid(), tab = await chrome.tabs.get(b.tab_id);
    valid();
    if (!allowed(tab.url)) { stop('绑定标签页已离开小红书'); throw Error('绑定标签页已离开小红书'); }
    if (tab.discarded || tab.frozen) {
      const reason = tab.discarded ? '页面已被 Chrome 释放' : '页面已被 Chrome 冻结';
      stop(reason + '，请打开该页后重新开启接管；不会自动刷新或抢回前台');
      throw Error(reason);
    }
    b.url = tab.url.split('?')[0]; b.title = pageTitle(tab);
    b.visibility = tab.active ? 'selected' : 'background';
    b.window_state = (await chrome.windows.get(tab.windowId)).state || 'normal'; valid();
    if (getJob() && Date.now() / 1000 >= getJob().expires) throw Error('操作已过期，未继续执行');
    return tab;
  }
  async function page(action, args, session, controlled) {
    const tab = await check(session, controlled);
    await bounded(chrome.scripting.executeScript({target: {tabId: tab.id}, world: 'MAIN', files: ['site.js']}), 8000, getJob()?.abort?.signal);
    await check(session, controlled);
    const context = {id: getJob()?.id || crypto.randomUUID(), expires: getJob()?.expires || Date.now() / 1000 + 35};
    const signal = getJob()?.abort?.signal;
    const pending = chrome.scripting.executeScript({target: {tabId: tab.id}, world: 'MAIN',
      func: (a, b, c) => xhsPageAction(a, b, c), args: [action, args, context]});
    let finished = false, pulseTimer;
    const pulse = async () => {
      try {
        await check(session, controlled);
        // CSS/history changes can settle without a DOM mutation. Inspect from
        // the worker so page timers/animation throttling cannot delay readiness.
        await bounded(chrome.scripting.executeScript({target: {tabId: tab.id}, world: 'MAIN',
          func: id => {window.__xhsResearchActions?.[id]?.inspect?.();}, args: [context.id]}), 2000, signal);
      } catch (_) { /* The main action owns its error and cancellation result. */ }
      finally {if (!finished) pulseTimer = setTimeout(pulse, 300);}
    };
    if (['open_note', 'close_note', 'preview', 'native_entry', 'creator_fixture'].includes(action)) pulseTimer = setTimeout(pulse, 300);
    const result = await bounded(pending, Math.max(1, context.expires * 1000 - Date.now()), signal)
      .finally(() => {finished = true; clearTimeout(pulseTimer);});
    await check(session, controlled);
    const data = result[0]?.result;
    if (!data) throw Error('网页未返回可读取结果');
    if (data.adapter_error) {const error=Error(data.adapter_error);error.recoverable=data.adapter_recoverable===true;throw error;}
    if (data.blocked) { stop('平台提示：' + data.blocked); await post('/bridge/pause', {reason: data.blocked}); throw Error('平台要求处理验证或登录，已停止'); }
    return data;
  }
  async function site(action, args = {}, controlled = false) {
    const session = getBinding()?.session;
    if (controlled && action !== 'identity') {
      const account = await page('identity', {}, session, controlled);
      if (!getBinding()?.account_id || account.user_id !== getBinding().account_id) {
        stop('登录账号无法确认或已改变，请重新核对并绑定'); throw Error('登录账号无法确认或已改变');
      }
    }
    const result = await page(action, args, session, controlled);
    if (controlled && action === 'identity' && (!result.user_id || result.user_id !== getBinding()?.account_id)) {
      stop('登录账号无法确认或已改变，请重新核对并绑定'); throw Error('登录账号无法确认或已改变');
    }
    return result;
  }
  async function images(raw, session) {
    const data = [], errors = []; let total = 0;
    for (const value of (raw.image_urls || []).slice(0, 12)) {
      await check(session);
      try {
        const url = new URL(value.startsWith('//') ? 'https:' + value : value);
        if (url.protocol === 'http:' && url.hostname.endsWith('.xhscdn.com')) url.protocol = 'https:';
        if (url.protocol !== 'https:' || !url.hostname.endsWith('.xhscdn.com')) throw Error('图片域名未授权');
        const bytes = await imageBytes(url.href, getJob()?.abort?.signal); await check(session);
        if (bytes.byteLength > 4500000 || total + bytes.byteLength > 12000000) throw Error('图片超过本篇保存上限');
        total += bytes.byteLength; let binary = ''; const arr = new Uint8Array(bytes);
        for (let i = 0; i < arr.length; i += 16384) binary += String.fromCharCode(...arr.subarray(i, i + 16384));
        data.push(btoa(binary));
      } catch (e) { errors.push(e.message); }
    }
    await check(session);
    return {...raw, image_data: data, image_errors: errors};
  }
  async function execute(action, args = {}, controlled = false) {
    if (!['snapshot', 'search', 'open_note', 'read_note', 'close_note', 'scroll', 'identity', 'preview', 'preview_status', 'native_entry', 'open_editor', 'creator_inspect', 'creator_navigate', 'creator_fixture'].includes(action)) throw Error('未开放此站内动作');
    if (action === 'preview' && (!Array.isArray(args.images) || args.images.length < 3 || args.images.length > 12)) throw Error('预览图片包无效');
    if (action === 'open_editor') {
      const session = getBinding()?.session, expected = getBinding()?.account_id;
      const tab = await check(session, controlled);
      const current = await site('identity', {}, controlled);
      if (!expected || current.user_id !== expected) throw Error('打开编辑器前账号无法核对');
      if (new URL(tab.url).hostname !== 'creator.xiaohongshu.com')
        await chrome.tabs.update(tab.id, {active: true, url: 'https://creator.xiaohongshu.com/publish/publish?source=official'});
      else await chrome.tabs.update(tab.id, {active: true});
      await chrome.windows.update(tab.windowId, {focused: true});
      const deadline = Math.min(Date.now() + 20000, (getJob()?.expires || Infinity) * 1000);
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 300));
        const loaded = await check(session, controlled);
        if (loaded.status !== 'complete' || new URL(loaded.url).hostname !== 'creator.xiaohongshu.com') continue;
        const user = await page('identity', {}, session, controlled);
        if (!user.user_id) continue;
        if (user.user_id !== expected) {stop('创作者账号已改变，请重新绑定');throw Error('创作者账号与原绑定不一致');}
        return {opened: true, account_id: expected, published: false};
      }
      throw Error('创作者中心未能在时限内核对同一账号，请正常登录后重试');
    }
    if (action === 'search') {
      if (typeof args.keyword !== 'string' || !args.keyword.trim() || args.keyword.length > 100) throw Error('关键词无效');
      const session = getBinding()?.session, tab = await check(session, controlled);
      const user = await site('identity', {}, controlled);
      if (controlled && (!getBinding().account_id || user.user_id !== getBinding().account_id)) { stop('账号改变或无法核对，未执行搜索'); throw Error('账号改变或无法核对'); }
      const url = new URL('https://www.xiaohongshu.com/search_result');
      url.searchParams.set('keyword', args.keyword); url.searchParams.set('source', 'web_explore_feed');
      await chrome.tabs.update(tab.id, {url: url.href});
      const until = Math.min(Date.now() + 25000, (getJob()?.expires || Infinity) * 1000);
      while (Date.now() < until) {
        await new Promise(r => setTimeout(r, 300)); const current = await check(session, controlled);
        if (current.status === 'complete' && new URL(current.url).pathname === '/search_result' && new URL(current.url).searchParams.get('keyword') === args.keyword) {
          const result = await site('snapshot', {}, controlled); if (result.keyword === args.keyword && result.cards.length) return result;
        }
      }
      throw Error('搜索页未在时限内加载，未读取旧列表');
    }
    const session = getBinding()?.session, data = await site(action, args, controlled);
    return action === 'read_note' ? images(data, session) : data;
  }
  return {check, execute, site};
}
function bounded(promise, ms, signal) {
  let timer, cancel;
  return Promise.race([promise, new Promise((_, reject) => {
    cancel = () => reject(Error('操作已停止'));
    if (signal?.aborted) return cancel();
    signal?.addEventListener('abort', cancel, {once: true});
    timer = setTimeout(() => reject(Error('页面操作超时，已停止；未自动重试')), ms);
  })]).finally(() => {clearTimeout(timer); signal?.removeEventListener('abort', cancel);});
}
async function imageBytes(url, signal) {
  const abort = new AbortController(), cancel = () => abort.abort(), timer = setTimeout(cancel, 8000);
  if (signal?.aborted) cancel(); else signal?.addEventListener('abort', cancel, {once: true});
  try {
    const response = await fetch(url, {credentials: 'omit', redirect: 'error', signal: abort.signal});
    if (!response.ok) throw Error('HTTP ' + response.status);
    return await response.arrayBuffer();
  } finally {clearTimeout(timer); signal?.removeEventListener('abort', cancel);}
}
function pageTitle(tab) {
  const url = new URL(tab.url);
  if (url.hostname === 'creator.xiaohongshu.com') return '小红书创作者中心 · ' + (tab.title || '编辑页面');
  if (url.pathname === '/search_result') return '小红书搜索：' + (url.searchParams.get('keyword') || '未指定关键词');
  return tab.title || '小红书';
}
