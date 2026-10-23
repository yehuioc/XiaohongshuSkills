const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const crypto=require('node:crypto');
const flush=()=>new Promise(r=>setImmediate(r));
function event(){const listeners=[];return {addListener:fn=>listeners.push(fn),emit:(...args)=>listeners.forEach(fn=>fn(...args))};}
const account='a'.repeat(24), origin='chrome-extension://'+'a'.repeat(32);
function fixture(options={}){
 const events={message:event(),connect:event(),alarm:event(),startup:event(),installed:event(),removed:event(),updated:event()};
 const timers=new Map(), polls=[],results=[],updates=[],scripts=[];let sequence=0;
 let tab={id:123,windowId:45,title:'测试研究页',url:'https://www.xiaohongshu.com/explore',status:'complete',active:false,autoDiscardable:true};
 const saved=options.saved===false?{}:options.saved||{runnerState:{binding:{tab_id:123,instance:crypto.randomUUID(),revision:4,runner:'background',session:crypto.randomUUID(),control:true,grant_at:Date.now()/1000,account_id:account,auto_discardable:true}}};
 const commands=[];let pollReply=null;
 const chrome={runtime:{id:'a'.repeat(32),getURL:p=>origin+'/'+p,getManifest:()=>({version:'0.2.0'}),onMessage:events.message,onConnect:events.connect,onStartup:events.startup,onInstalled:events.installed},
 sidePanel:{setPanelBehavior:async()=>{}},alarms:{create:async()=>{},clear:async()=>{},onAlarm:events.alarm},
 storage:{local:{get:async()=>({token:'test-only-token'}),set:async()=>{}},session:{get:async()=>saved,set:async value=>Object.assign(saved,structuredClone(value))}},
 tabs:{get:async id=>{assert.equal(id,123);return {...tab};},query:async()=>[tab],update:async(id,patch)=>{updates.push({id,...patch});Object.assign(tab,patch);if(patch.url)options.afterNavigate?.(context);return {...tab};},onRemoved:events.removed,onUpdated:events.updated},
 windows:{get:async()=>({state:options.windowState||'minimized'}),update:async()=>{if(!options.allowFocus)throw Error('Background work must not focus or restore a window');}},
 scripting:{executeScript:async config=>{
  scripts.push(config);if(config.files||config.world==='ISOLATED')return [{}];
  const [action]=config.args;
  if(action==='identity')return [{result:{user_id:options.account||account}}];
  if(['snapshot','open_note','read_note','close_note','preview','native_entry','creator_inspect','creator_navigate'].includes(action)){
   if(options.page)return options.page(action,config);
   return [{result:{cards:[{note_id:'b'.repeat(24),title:'已加载卡片'}],keyword:new URL(tab.url).searchParams.get('keyword')}}];
  }
  options.inspector?.(config.args[0]); return [{}];
 }}};
 const context=vm.createContext({chrome,crypto:crypto.webcrypto,URL,AbortController,AbortSignal,Date,structuredClone,btoa,Uint8Array,
  setTimeout:(fn,ms)=>{const id=++sequence;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
  fetch:async(url,init)=>{const body=JSON.parse(init.body);let result;
   if(url.endsWith('/bridge/poll')){polls.push(body);result=!body.binding.control?null:pollReply?pollReply(body):body.busy?null:commands.shift()||null;}
   else if(url.endsWith('/bridge/result')){results.push(body);result={accepted:true};}else result={};
   if(options.networkError)throw Error('local server offline');
   return {ok:true,json:async()=>({result})};
  }});
 context.importScripts=name=>vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension',name),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/background.js'),'utf8'),context);
 return {context,events,polls,results,updates,scripts,timers,saved,commands,get tab(){return tab;},set tab(value){tab={...tab,...value};},set pollReply(fn){pollReply=fn;},
  async ready(){await context.init();await flush();},async tick(){await context.tick();await flush();await flush();},
  command(action='snapshot'){const b=context.state().binding;const c={id:crypto.randomUUID(),action,args:{},session:b.session,expires:Date.now()/1000+40};commands.push(c);return c;},
  panel(){const port={name:'xhs-panel',sender:{id:chrome.runtime.id,url:chrome.runtime.getURL('panel.html')},onDisconnect:event(),postMessage(){},disconnect(){}};events.connect.emit(port);return port;}
 };
}
test('background tab executes with no panel, no DOM, no window focus and schedules another heartbeat',async()=>{
 const f=fixture();await f.ready();f.command();await f.tick();assert.equal(f.results.length,1);assert.equal(f.results[0].result.cards.length,1);
 assert.equal(f.context.state().binding.control,true);assert.equal(f.polls[0].binding.visibility,'background');
 assert.equal(f.polls[0].binding.window_state,'minimized');
 assert.equal(f.updates.some(p=>p.active),false);await f.tick();assert.ok([...f.timers.values()].some(t=>t.ms===1500));
});
test('creator research uses the same controlled worker and preserves grant on rejected navigation',async()=>{
 const f=fixture({page:action=>Promise.resolve([{result:action==='creator_inspect'?{text:'真实创作者页'}:{adapter_error:'编辑器已有内容，未导航',adapter_recoverable:true}}])});
 await f.ready();f.tab={url:'https://creator.xiaohongshu.com/new/note-manager'};
 f.command('creator_inspect');await f.tick();assert.equal(f.results[0].result.text,'真实创作者页');
 f.command('creator_navigate');await f.tick();assert.match(f.results[1].error,/已有内容/);assert.equal(f.context.state().binding.control,true);
 assert.equal(f.updates.some(p=>p.active||p.url),false);
});
test('a new marker owner replaces an old revision, while delayed older paints cannot overwrite it',async()=>{
 const f=fixture();await f.ready();
 const box={dataset:{revision:'99'},style:{},textContent:'旧实例显示'};
 f.context.document={getElementById:()=>box};
 await f.context.markPage();const paint=f.scripts.findLast(s=>s.world==='ISOLATED');
 paint.func(...paint.args);assert.match(box.textContent,/后台操作/);assert.equal(box.dataset.instance,paint.args[2]);
 const before=box.textContent;
 paint.func(false,1000,'old-owner',paint.args[3]-1);assert.equal(box.textContent,before);
 paint.func(false,0,paint.args[2],paint.args[3]+1);assert.equal(box.textContent,before);
});
test('closing and reopening all panels preserves one background owner and its grant',async()=>{
 const f=fixture();await f.ready();const before=f.context.state().binding;const p=f.panel();await flush();p.onDisconnect.emit();
 f.command();await f.tick();const again=f.panel();await flush();assert.equal(f.context.state().binding.session,before.session);
 assert.equal(f.context.state().binding.control,true);assert.equal(f.results.length,1);again.onDisconnect.emit();
});
test('slow page action keeps polling and receives workbench stop while still awaiting the page',async()=>{
 let finish;const f=fixture({page:()=>new Promise(r=>finish=r)});await f.ready();f.command();await f.tick();
 assert.equal(f.context.state().busy,true);f.pollReply=()=>({stop:true});await f.tick();
 assert.equal(f.polls[1].busy,true);assert.ok(f.polls[1].executing.id);assert.equal(f.context.state().binding.control,false);
 assert.equal(f.context.state().busy,false);assert.match(f.results[0].error,/停止/);assert.equal(f.results[0].result,null);
 finish([{result:{cards:['late-result']}}]);await flush();assert.equal(f.results.length,1);
 assert.ok(f.updates.some(p=>p.autoDiscardable===true));
});
test('same-browser idle worker restart preserves grant; in-flight crash never repeats an action',async()=>{
 const f=fixture();await f.ready();const first=f.context.state().binding;
 const resumed=fixture({saved:structuredClone(f.saved)});await resumed.ready();assert.equal(resumed.context.state().binding.session,first.session);assert.equal(resumed.context.state().binding.control,true);
 const crashed=structuredClone(f.saved);crashed.runnerState.flight={id:crypto.randomUUID(),session:first.session,remote:true};
 const recovery=fixture({saved:crashed});await recovery.ready();assert.equal(recovery.context.state().binding.control,false);assert.match(recovery.context.state().message,/中断/);
 assert.equal(recovery.scripts.filter(s=>['snapshot','preview'].includes(s.args?.[0])).length,0);assert.match(recovery.results[0].error,/未自动重放/);
});
test('browser restart without session storage never restores control',async()=>{
 const f=fixture({saved:false});await f.ready();assert.equal(f.context.state().paired,true);assert.equal(f.context.state().binding,null);assert.equal(f.polls.length,0);
});
test('frozen or discarded target pauses instead of stealing foreground or refreshing it',async()=>{
 for(const field of ['frozen','discarded']){
  const f=fixture();await f.ready();f.tab={[field]:true};f.command();await f.tick();
  assert.equal(f.context.state().binding.control,false);assert.equal(f.results.length,0);assert.match(f.context.state().message,/冻结|释放/);
  assert.equal(f.updates.some(p=>p.active||p.url),false);
 }
});
test('offline server and changed account do not silently restore a grant',async()=>{
 const offline=fixture({networkError:true});await offline.ready();await offline.tick();assert.equal(offline.context.state().binding.control,false);assert.match(offline.context.state().message,/连接中断/);
 const changed=fixture({account:'b'.repeat(24)});await changed.ready();assert.equal(changed.context.state().binding.control,false);
});
test('stop raced against a late heartbeat cannot execute its returned command',async()=>{
 const f=fixture();await f.ready();const command=f.command();f.pollReply=()=>{f.context.stop();return command;};await f.tick();
 assert.equal(f.results.length,0);assert.equal(f.context.state().binding.control,false);assert.equal(f.scripts.some(s=>s.args?.[0]==='snapshot'),false);
});
test('expired or cancelled server command stops without accepting a late page result',async()=>{
 const f=fixture({page:()=>new Promise(()=>{})});await f.ready();const command=f.command();await f.tick();
 f.pollReply=()=>({cancel:command.id});await f.tick();assert.equal(f.context.state().busy,false);assert.equal(f.context.state().binding.control,false);assert.match(f.results[0].error,/停止/);
});
test('unknown RPC and webpage callers cannot gain script or publishing capabilities',async()=>{
 const f=fixture();await f.ready();await assert.rejects(()=>f.context.handle('publish'),/未开放/);
 let replied=false;const returns=f.events.message.emit({action:'control',args:{enabled:true}},{id:'untrusted',url:'https://www.xiaohongshu.com/explore'},()=>replied=true);
 await flush();assert.equal(replied,false);
});
test('search targets the fixed background tab, waits for the matching URL and never focuses Chrome',async()=>{
 const f=fixture();await f.ready();const result=vm.runInContext("executor.execute('search',{keyword:'图文 排版'},true)",f.context);
 await flush();const settle=[...f.timers.values()].find(t=>t.ms===300);assert.ok(settle);settle.fn();
 const listing=await result;assert.equal(listing.keyword,'图文 排版');
 const navigate=f.updates.find(p=>p.url);assert.equal(navigate.id,123);assert.equal(navigate.active,undefined);
 assert.equal(new URL(navigate.url).searchParams.get('keyword'),'图文 排版');
});
test('stop during background navigation prevents all subsequent page reads',async()=>{
 const f=fixture({afterNavigate:context=>context.stop()});await f.ready();
 const result=vm.runInContext("executor.execute('search',{keyword:'测试'},true)",f.context);
 await flush();[...f.timers.values()].find(t=>t.ms===300).fn();await assert.rejects(()=>result,/接管已停止/);
 assert.equal(f.scripts.some(s=>s.args?.[0]==='snapshot'),false);
});

test('local stop with every panel closed immediately reports revocation and restores discard preference',async()=>{
 const f=fixture();await f.ready();const before=f.context.state().binding;
 f.context.stop('本地停止测试');await flush();
 const sent=f.polls[0];assert.equal(sent.binding.control,false);assert.ok(sent.binding.revision>before.revision);
 assert.notEqual(sent.binding.session,before.session);assert.match(sent.status,/本地停止/);
 assert.ok(f.updates.some(p=>p.autoDiscardable===true));
});
test('removed tab reports stop immediately and an intentionally empty owner never revives a legacy binding',async()=>{
 const f=fixture();await f.ready();f.events.removed.emit(123);await flush();await flush();
 assert.equal(f.context.state().binding,null);assert.ok(f.polls.some(p=>p.binding.control===false));
 const empty=fixture({saved:{runnerState:{binding:null},lastBinding:{tab_id:123,account_id:account}}});await empty.ready();
 assert.equal(empty.context.state().binding,null);
});
test('controlled identity inspection also stops on account drift',async()=>{
 const options={},f=fixture(options);await f.ready();options.account='b'.repeat(24);f.command('identity');await f.tick();
 assert.equal(f.context.state().binding.control,false);assert.match(f.results[0].error,/账号/);
 assert.match(f.context.state().message,/账号/);
});

test('worker readiness pulses finish a hidden close even when page observers never fire',async()=>{
 let finish;const f=fixture({page:()=>new Promise(r=>finish=r),inspector:()=>finish([{result:{closed:true}}])});
 await f.ready();f.command('close_note');await f.tick();assert.equal(f.context.state().busy,true);
 const pulse=[...f.timers.values()].find(t=>t.ms===300);assert.ok(pulse);await pulse.fn();await flush();await flush();
 assert.equal(f.results[0].result.closed,true);assert.equal(f.context.state().busy,false);
 assert.equal(f.updates.some(p=>p.active||p.url),false);
});

test('user opening the creator editor keeps the same grant only after matching account verification',async()=>{
 const f=fixture({allowFocus:true});await f.ready();const before=f.context.state().binding;
 const pending=f.context.handle('open_editor');await flush();await flush();
 [...f.timers.values()].find(t=>t.ms===300).fn();await pending;
 assert.equal(f.context.state().binding.control,true);assert.equal(f.context.state().binding.session,before.session);
 assert.equal(new URL(f.tab.url).hostname,'creator.xiaohongshu.com');
 assert.match(f.context.state().message,/同一账号/);
});
test('stop while opening the creator editor never restores control',async()=>{
 const f=fixture({allowFocus:true,afterNavigate:c=>c.stop()});await f.ready();
 const pending=f.context.handle('open_editor');await flush();await flush();
 [...f.timers.values()].find(t=>t.ms===300)?.fn();
 await assert.rejects(()=>pending,/停止/);assert.equal(f.context.state().binding.control,false);
});

test('recoverable native validation stops only the job and retains the explicit user grant',async()=>{
 const f=fixture({page:()=>[{result:{adapter_error:'原生文字编辑器已有其他内容，未覆盖',adapter_recoverable:true}}]});
 await f.ready();f.command('native_entry');await f.tick();
 assert.equal(f.context.state().binding.control,true);assert.equal(f.results[0].result,null);assert.match(f.results[0].error,/未覆盖/);
});
