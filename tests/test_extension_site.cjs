const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../extension/site.js'),'utf8');
const A='a'.repeat(24), B='b'.repeat(24);
function node(text=''){return {innerText:text,getClientRects:()=>[{}],querySelector:()=>null,querySelectorAll:()=>[]};}
function fixture(id=A,detail={}){
 const body=node('页面正常');const root=node();
 const values={'#detail-desc,.desc':node(detail.text||''),'#detail-title,.title':node(detail.title||'')};
 root.querySelector=s=>values[s]||null;
 root.querySelectorAll=s=>s.includes('comment-item')?[node('已加载的评论')]:[];
 const document={body,querySelector:s=>s.includes('note-detail-mask')?root:null,querySelectorAll:s=>s==='.note-detail-mask,.note-container'?[root]:[]};
 const location={hostname:'www.xiaohongshu.com',origin:'https://www.xiaohongshu.com',pathname:'/explore/'+id,href:'https://www.xiaohongshu.com/explore/'+id};
 const window={__INITIAL_STATE__:{note:{noteDetailMap:detail.map||{}}}};
 const context=vm.createContext({window,document,location,URL,Date,Event,KeyboardEvent:Event,setTimeout:fn=>{fn();}});
 vm.runInContext(code,context);return context;
}
test('rejects a changed note URL and never substitutes the single stale cache entry',async()=>{
 const different=fixture(B,{text:'另一篇详情'});
 await assert.rejects(()=>different.xhsRunAction('read_note',{note_id:A}),/地址与目标/);
 const stale=fixture(A,{map:{[B]:{note:{noteId:B,title:'旧文章',desc:'旧正文'}}}});
 stale.document.querySelectorAll('.note-detail-mask,.note-container')[0].querySelectorAll=()=>[];
 await assert.rejects(()=>stale.xhsRunAction('read_note',{note_id:A}),/未读到正文|未找到|列表摘要/);
});
test('captures the matching modal body and loaded comments with exact note identity',async()=>{
 const context=fixture(A,{title:'真实详情标题',text:'明确的详情正文',map:{[A]:{note:{noteId:A,time:1,desc:'明确的详情正文',imageList:[{urlDefault:'https://sns-webpic-qc.xhscdn.com/example'}],interactInfo:{likedCount:'10'}}}}});
 const result=await context.xhsRunAction('read_note',{note_id:A});
 assert.equal(result.note_id,A);assert.equal(result.title,'真实详情标题');assert.equal(result.text,'明确的详情正文');
 assert.deepEqual(Array.from(result.comments),['已加载的评论']);assert.equal(result.image_urls.length,1);assert.equal(result.metrics.likedCount,'10');
 assert.equal(result.image_data,undefined);
});
test('rejects mismatched cached note identity and arbitrary or publishing actions',async()=>{
 const context=fixture(A,{text:'正文',map:{[A]:{note:{noteId:B,desc:'错误身份'}}}});
 await assert.rejects(()=>context.xhsRunAction('read_note',{note_id:A}),/另一篇/);
 for(const action of ['evaluate','publish','like','comment'])await assert.rejects(()=>context.xhsRunAction(action,{script:'alert(1)'}),/未开放/);
});
test('creator identity reads only fixed user-info records and never returns credentials',async()=>{
 const context=fixture();context.location.hostname='creator.xiaohongshu.com';context.location.origin='https://creator.xiaohongshu.com';
 const queried=[];
 context.localStorage={getItem(key){queried.push(key);return key==='USER_INFO_FOR_BIZ'?JSON.stringify({userId:A,token:'never-export-this-value'}):null;}};
 const result=await context.xhsRunAction('identity',{});
 assert.equal(result.user_id,A);assert.equal(result.verification,'creator_user_info');
 assert.deepEqual(queried,['USER_INFO','USER_INFO_FOR_BIZ','snsWebPublishCurrentUser']);
 assert.equal(JSON.stringify(result).includes('never-export'),false);
});

function pendingModal(){
 const context=fixture();let observer,clicked=0,root=null;
 context.AbortController=AbortController;context.clearTimeout=()=>{};
 context.MutationObserver=class{constructor(callback){observer=callback;}observe(){}disconnect(){}};
 context.setTimeout=()=>1;
 const link={href:'https://www.xiaohongshu.com/explore/'+A,getClientRects:()=>[{}],click(){clicked++;}};
 context.document.querySelectorAll=s=>s==='section.note-item a[href],.note-item a[href]'?[link]:s==='.note-detail-mask,.note-container'&&root?[root]:[];
 context.document.querySelector=()=>root;context.document.documentElement={};
 context.location.href='https://www.xiaohongshu.com/explore';
 return {context,get clicked(){return clicked;},open(notify=true,complete=true){if(complete)context.window.__INITIAL_STATE__.note.noteDetailMap[A]={note:{noteId:A,desc:'完整正文',time:1,interactInfo:{}}};context.location.href='https://www.xiaohongshu.com/explore/'+A;root=node('真实弹层');if(notify)observer();}};
}
test('hidden modal readiness completes from DOM observation without any timer firing',async()=>{
 const f=pendingModal();const result=f.context.xhsPageAction('open_note',{note_id:A},{id:'test-hidden',expires:Date.now()/1000+30});
 assert.equal(f.clicked,1);f.open();assert.equal((await result).opened,true);
});
test('stop aborts a waiting modal and an expired command never clicks',async()=>{
 const f=pendingModal();const result=f.context.xhsPageAction('open_note',{note_id:A},{id:'test-stop',expires:Date.now()/1000+30});
 f.context.window.__xhsResearchActions['test-stop'].abort.abort();assert.match((await result).adapter_error,/停止/);
 assert.equal(f.context.window.__xhsResearchActions['test-stop'],undefined);
 const expired=pendingModal();const rejected=await expired.context.xhsPageAction('open_note',{note_id:A},{id:'expired',expires:Date.now()/1000-1});
 assert.match(rejected.adapter_error,/过期/);assert.equal(expired.clicked,0);
});

test('stopping after image selection prevents deferred preview text from being filled',async()=>{
 const context=fixture();context.AbortController=AbortController;context.clearTimeout=()=>{};context.setTimeout=()=>1;
 context.location.hostname='creator.xiaohongshu.com';context.localStorage={getItem:()=>null};context.document.documentElement={};
 let observed,selected=0,inserted=0;
 context.MutationObserver=class{constructor(callback){observed=callback;}observe(){}disconnect(){}};
 context.atob=atob;context.Uint8Array=Uint8Array;context.File=File;
 context.DataTransfer=class{constructor(){this.files=[];this.items={add:file=>this.files.push(file)};}};
 const upload={accept:'image/png',files:[],dispatchEvent(){selected=this.files.length;}};
 context.document.querySelector=()=>null;context.document.querySelectorAll=s=>s==='input[type="file"]'?[upload]:[];
 context.document.execCommand=()=>inserted++;
 const result=context.xhsPageAction('preview',{images:['AA==','AA==','AA=='],title:'不应填入',body:'不应填入'},{id:'preview-stop',expires:Date.now()/1000+30});
 assert.equal(selected,3);context.window.__xhsResearchActions['preview-stop'].abort.abort();
 assert.match((await result).adapter_error,/停止/);observed();assert.equal(inserted,0);
});

test('the fixed worker inspector can finish readiness when no DOM event or page timer fires',async()=>{
 const f=pendingModal();const result=f.context.xhsPageAction('open_note',{note_id:A},{id:'worker-pulse',expires:Date.now()/1000+30});
 f.open(false);f.context.window.__xhsResearchActions['worker-pulse'].inspect();assert.equal((await result).opened,true);
 assert.equal(f.context.window.__xhsResearchActions['worker-pulse'],undefined);
});

test('a matching visible modal seeded with a card cannot pass for complete detail',async()=>{
 const f=pendingModal();let finished=false;
 const result=f.context.xhsPageAction('open_note',{note_id:A},{id:'detail-loading',expires:Date.now()/1000+30}).then(value=>{finished=true;return value;});
 f.context.window.__INITIAL_STATE__.note.noteDetailMap[A]={note:{noteId:A,title:'卡片标题',imageList:[{urlDefault:'https://image.xhscdn.com/cover'}]}};
 f.open(true,false);await Promise.resolve();assert.equal(finished,false);
 const rejected=await f.context.xhsPageAction('read_note',{note_id:A},{id:'read-too-early',expires:Date.now()/1000+30});
 assert.match(rejected.adapter_error,/列表摘要/);
 f.open();assert.equal((await result).detail_ready,true);
});
test('fully loaded pure-image detail is still accepted without requiring nonempty prose',async()=>{
 const context=fixture(A,{map:{[A]:{note:{noteId:A,time:1,desc:'',interactInfo:{},imageList:[{urlDefault:'https://image.xhscdn.com/real-image'}]}}}});
 const result=await context.xhsRunAction('read_note',{note_id:A});
 assert.equal(result.text,'');assert.equal(result.image_urls.length,1);assert.equal(result.extraction.detail_ready,true);
});


function nativeFixture(initial='write'){
 const c=fixture();c.location.hostname='creator.xiaohongshu.com';c.localStorage={getItem:()=>null};let phase=initial,wall=1000,pending;
 let generated=0,advanced=0,styleClicks=0,checks=0,defaultCaption=false;const url='https://sns.xhscdn.com/native.jpg';
 const decode=value=>typeof value==='string'?value.replace(/<br[^>]*>/g,'\n').replace(/<\/p><p>/g,'\n\n').replace(/<[^>]+>/g,''):value.content.map(p=>(p.content||[]).map(n=>n.type==='hardBreak'?'\n':n.text||'').join('')).join('\n\n');
 const saved=['原生正文\n\n第二段'];const boxes=[];
 function makeBox(value=''){
  const box=node(value),index=boxes.length;box.focus=()=>{};box.dispatchEvent=()=>{};
  box.editor={isInitialized:true,state:{tr:{}},commands:{setContent(value){box.lastDocument=value;box.innerText=decode(value);}},emit(){pending={index,value:box.innerText,at:wall+300};}};
  boxes.push(box);return box;
 }
 const box=makeBox(saved[0]),body=node(''),title={value:''};body.editor={commands:{setContent(value){body.innerText=decode(value);}}};
 c.Date={now:()=>wall};
 const imageList=()=>saved.filter(Boolean).map((_,i)=>({src:url+i,currentSrc:url+i,complete:true,naturalWidth:1200}));
 const active={value:true};const choice={classList:{contains:()=>active.value},click(){styleClicks++;active.value=true;}};
 const container={querySelector:s=>s==='.cover-name'?node('简约'):choice};choice.closest=()=>container;
 const generate={...node('生成图片'),disabled:false,getAttribute:()=>null,click(){generated++;phase='templates';}};
 const next={...node('下一步'),disabled:false,getAttribute:()=>null,click(){advanced++;phase='final';if(defaultCaption)body.innerText=saved[0];}};
 const add={...node('再写一张'),click(){if(saved.every(Boolean)){makeBox();saved.push('');}}};
 const root={...node('预览图片'),querySelectorAll:()=>[next]};
 c.document.body={get innerText(){return phase==='write'?'写文字 生成图片':phase==='templates'?'预览图片 选择一个喜欢的卡片 下一步':'发布笔记';}};
 c.document.querySelector=s=>{
  if(s==='.image-overview')return phase==='templates'?root:null;
  if(s==='.cover-item.active')return choice;
  if(s==='.overview-footer')return root;
  if(s==='.add-text-item-button')return add;
  if(s.includes('ProseMirror'))return phase==='final'?body:null;
  if(s.includes('input[placeholder'))return phase==='final'?title:null;
  return null;
 };
 c.document.querySelectorAll=s=>{
  if(s==='[role="textbox"][contenteditable="true"]')return phase==='write'?boxes:[];
  if(s==='.image-overview .swiper-img')return phase==='templates'?imageList():[];
  if(s==='.cover-item-container')return [container];
  if(s==='.img-preview-area .pr')return phase==='final'?imageList():[];
  if(s.startsWith('button,[role="button"],.d-button'))return phase==='write'?[generate]:[next];
  return [];
 };
 c.HTMLInputElement=function(){};Object.defineProperty(c.HTMLInputElement.prototype,'value',{set(value){this.value=value;}});title.dispatchEvent=()=>{};
 const utilities={visible:e=>!!e,text:e=>e?.innerText?.trim()||'',check:()=>{checks++;},until:async predicate=>{
  for(let i=0;i<5;i++){const result=predicate();if(result)return result;wall+=500;if(pending&&wall>=pending.at){saved[pending.index]=pending.value;pending=null;}}
  throw Error('test readiness did not settle');
 },identity:()=>({user_id:A})};
 return {c,box,boxes,body,url:url+'0',saved,utilities,setNativeDefault(){defaultCaption=true;},args:{draft_id:'draft',revision:'revision',text:'原生正文\n第二段',title:'最终标题',body:'最终正文 #话题'},get counts(){return {generated,advanced,styleClicks,checks};}};
}
test('native workflow verifies paragraphs, selects template, fills final metadata, and never regenerates on repeat',async()=>{
 const f=nativeFixture();const r=await f.c.xhsNativePreview({...f.args,template:'简约'},f.utilities);
 assert.equal(r.ready,true);assert.equal(r.published,false);assert.equal(r.title,'最终标题');assert.equal(r.body,'最终正文 #话题');assert.equal(r.image_count,1);
 const repeated=await f.c.xhsNativePreview(f.args,f.utilities);assert.equal(repeated.ready,true);assert.equal(f.counts.generated,1);assert.equal(f.counts.advanced,1);
});
test('native workflow refuses unrelated existing text and unassociated generated images',async()=>{
 const f=nativeFixture();f.box.innerText='另一份尚未保存的文稿';await assert.rejects(()=>f.c.xhsNativePreview(f.args,f.utilities),/已有其他内容/);assert.equal(f.counts.generated,0);
 const orphan=nativeFixture('templates');await assert.rejects(()=>orphan.c.xhsNativePreview(orphan.args,orphan.utilities),/未关联/);assert.equal(orphan.counts.advanced,0);
 const adopted=await orphan.c.xhsNativePreview({...orphan.args,resume_images:[orphan.url]},orphan.utilities);assert.equal(adopted.ready,true);assert.equal(orphan.counts.generated,0);
});
test('native workflow preserves an existing final caption instead of overwriting it',async()=>{
 const f=nativeFixture();await f.c.xhsNativePreview(f.args,f.utilities);f.body.innerText='用户后来自己编辑的内容';
 await assert.rejects(()=>f.c.xhsNativePreview(f.args,f.utilities),/已有其他正文/);assert.equal(f.body.innerText,'用户后来自己编辑的内容');assert.equal(f.counts.generated,1);
});

test('requesting another template after final preview never silently succeeds',async()=>{
 const f=nativeFixture();await f.c.xhsNativePreview(f.args,f.utilities);
 await assert.rejects(()=>f.c.xhsNativePreview({...f.args,template:'科技'},f.utilities),/不能静默更换/);
 assert.equal(f.counts.generated,1);assert.equal(f.counts.advanced,1);
});

test('multiple native cards wait for the shared save debounce and preserve manual line breaks',async()=>{
 const f=nativeFixture();f.box.innerText='';f.saved[0]='';
 const text=['先读一页课件。'.repeat(6),'用自己的话回答问题。'.repeat(5),'回到原文核对遗漏。'.repeat(5)].join('\n\n');
 const r=await f.c.xhsNativePreview({...f.args,text},f.utilities);
 assert.equal(r.ready,true);assert.ok(r.image_count>1);
 assert.equal(f.saved.join('').replace(/\s/g,''),text.replace(/\s/g,''));
 assert.ok(f.saved.some(value=>value.includes('\n'))||f.saved.length>=3);
 assert.equal(f.counts.generated,1);
});
test('native line breaks use the platform manual-break schema',async()=>{
 const f=nativeFixture();await f.c.xhsNativePreview(f.args,f.utilities);
 const breaks=f.box.lastDocument.content[0].content.filter(n=>n.type==='hardBreak');
 assert.ok(breaks.length);assert.ok(breaks.every(n=>n.attrs['data-break-type']==='manual'));
 assert.equal(f.saved[0],f.args.text);
});
test('native text above the full-platform limit is rejected before any page mutation',async()=>{
 const f=nativeFixture();const original=f.box.innerText;
 await assert.rejects(()=>f.c.xhsNativePreview({...f.args,text:'字'.repeat(501)},f.utilities),/500/);
 assert.equal(f.box.innerText,original);assert.equal(f.counts.generated,0);
});

test('only an exact snapshot of a failed task-owned writing buffer can resume',async()=>{
 const f=nativeFixture();f.box.innerText='本轮失败后保留的部分文字';
 f.c.window.__xhsNativePreview={key:'draft:revision',text:f.args.text,phase:'writing',writing_snapshot:[f.box.innerText]};
 assert.equal((await f.c.xhsNativePreview(f.args,f.utilities)).ready,true);
 const edited=nativeFixture();edited.box.innerText='用户后来修改过的文字';
 edited.c.window.__xhsNativePreview={key:'draft:revision',text:edited.args.text,phase:'writing',writing_snapshot:['本轮失败后保留的部分文字']};
 await assert.rejects(()=>edited.c.xhsNativePreview(edited.args,edited.utilities),/已有其他内容/);
 assert.equal(edited.counts.generated,0);assert.equal(edited.box.innerText,'用户后来修改过的文字');
});

test('native first-card automatic caption is replaced only while advancing the owned generation',async()=>{
 const f=nativeFixture();f.box.innerText='';f.saved[0]='';f.setNativeDefault();
 const text=['一段测试文字。'.repeat(8),'另一段测试文字。'.repeat(8)].join('\n\n');
 const r=await f.c.xhsNativePreview({...f.args,text},f.utilities);
 assert.equal(r.ready,true);assert.ok(r.image_count>1);assert.equal(f.body.innerText,f.args.body);
 f.body.innerText=f.saved[0];
 await assert.rejects(()=>f.c.xhsNativePreview({...f.args,text},f.utilities),/已有其他正文/);
 assert.equal(f.counts.generated,1);
});
