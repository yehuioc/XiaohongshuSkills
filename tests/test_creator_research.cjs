const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../extension/site.js'),'utf8');
test('creator click supplies focusin and a released mouse sequence without focusing Chrome',()=>{
 const events=[];
 const wrapper={focus(){events.push('focus');},dispatchEvent(e){events.push(e.type);}};
 const element={scrollIntoView(){},getBoundingClientRect:()=>({left:10,top:20,width:40,height:20}),closest:s=>s==='.d-select-wrapper'?wrapper:null,dispatchEvent(e){events.push(e.type);}};
 const c=vm.createContext({window:{},document:{querySelectorAll:()=>[wrapper]},MouseEvent:Event,FocusEvent:Event});vm.runInContext(code,c);
 c.xhsCreatorClick(element,()=>{});
 assert.deepEqual(events,['pointerover','mouseover','pointerdown','focus','focusin','mousedown','pointerup','mouseup','click']);
});

test('background entering surfaces are available without admitting hidden clones or leaving overlays',()=>{
 const c=vm.createContext({document:{visibilityState:'hidden'},location:{hostname:'creator.xiaohongshu.com'},getComputedStyle:e=>e.style});vm.runInContext(code,c);
 const mask={getClientRects:()=>[{}],getAttribute:()=>null,hasAttribute:()=>false,matches:()=>true,style:{display:'block',visibility:'visible',opacity:'0'}};
 const node={...mask,matches:()=>false,style:{...mask.style,opacity:'1'},parentElement:mask};
 assert.equal(c.xhsElementVisible(node),false);assert.equal(c.xhsCreatorElementAvailable(node),true);
 mask.className='portal-fade-enter-from portal-fade-enter-active portal-fade-leave-active';assert.equal(c.xhsCreatorElementAvailable(node),false);mask.className='';
 mask.matches=()=>false;assert.equal(c.xhsCreatorElementAvailable(node),false);
 mask.matches=()=>true;c.document.visibilityState='visible';assert.equal(c.xhsCreatorElementAvailable(node),false);
});
function fixture({labels=['草稿箱(3)','上传图文'],dirty=false,href=null}={}) {
 let clicks=0;
 const node=label=>({innerText:label,children:[],tagName:'BUTTON',className:'',getClientRects:()=>[{}],getAttribute:key=>key==='href'?href:null,hasAttribute:()=>false,closest(){return this;},click(){clicks++;}});
 const nodes=labels.map(node),field={...node(''),value:dirty?'旧草稿':'',getAttribute:()=>null};
 const document={body:node('创作者页面'),querySelector:()=>null,querySelectorAll(selector){
  if(selector.startsWith('button,a,[role="button"]'))return nodes;
  if(selector.startsWith('input:not'))return dirty?[field]:[];
  if(selector.startsWith('button,a,input'))return nodes;
  return [];
 }};
 const location={hostname:'creator.xiaohongshu.com',origin:'https://creator.xiaohongshu.com',pathname:'/publish/publish',href:'https://creator.xiaohongshu.com/publish/publish'};
 const c=vm.createContext({document,location,URL,Date,window:{},atob,Uint8Array,crypto:require('node:crypto').webcrypto});vm.runInContext(code,c);
 const run=(action,args={})=>c.xhsCreatorResearch(action,args,{visible:e=>!!e,text:e=>e?.innerText?.trim()||'',check:()=>{},identity:()=>({user_id:'a'.repeat(24)})});
 return {c,run,get clicks(){return clicks;}};
}
test('creator inspection reports counted draft entry without clicking or exposing passwords',()=>{
 const f=fixture();const result=f.run('creator_inspect');
 assert.equal(result.navigation.find(n=>n.target==='drafts').matches,1);assert.equal(f.clicks,0);
});
test('creator navigation never accepts publish, deletion, supplied selector or arbitrary script',()=>{
 for(const target of ['发布','delete','submit','javascript:alert(1)','__proto__']){
  const f=fixture();assert.throws(()=>f.run('creator_navigate',{target,selector:'button'}),/未开放/);assert.equal(f.clicks,0);
 }
});
test('creator navigation refuses authored content and ambiguous entry labels',()=>{
 const dirty=fixture({dirty:true});assert.throws(()=>dirty.run('creator_navigate',{target:'images'}),/已有内容/);assert.equal(dirty.clicks,0);
 const duplicate=fixture({labels:['上传图文','上传图文']});assert.throws(()=>duplicate.run('creator_navigate',{target:'images'}),/不唯一/);assert.equal(duplicate.clicks,0);
});
test('creator navigation refuses external or destructive links and wrong site',()=>{
 for(const href of ['https://evil.example/','https://creator.xiaohongshu.com/delete/123']){
  const f=fixture({href});assert.throws(()=>f.run('creator_navigate',{target:'images'}),/超出/);assert.equal(f.clicks,0);
 }
 const f=fixture();f.c.location.hostname='www.xiaohongshu.com';assert.throws(()=>f.run('creator_inspect'),/创作者平台/);
});
test('creator navigation reports only a click, requiring a separate loaded-state inspection',()=>{
 const f=fixture();const r=f.run('creator_navigate',{target:'images'});assert.equal(f.clicks,1);assert.equal(r.published,false);assert.equal(r.ready,undefined);assert.match(r.message,/再次 creator_inspect/);
});
test('old upload inputs retained by the SPA cannot block note-manager navigation',()=>{
 const f=fixture({labels:['全部'],dirty:true});f.c.location.pathname='/new/note-manager';
 const result=f.run('creator_navigate',{target:'all'});
 assert.equal(result.clicked,true);assert.equal(f.clicks,1);
});
test('injected near-transparent tab clones and aria-hidden ancestors are not visible targets',()=>{
 const f=fixture();const element={getClientRects:()=>[{}],getAttribute:()=>null,hasAttribute:()=>false};
 f.c.getComputedStyle=()=>({visibility:'visible',display:'block',opacity:'0.00001'});
 assert.equal(f.c.xhsElementVisible(element),false);
 f.c.getComputedStyle=()=>({visibility:'visible',display:'block',opacity:'1'});
 element.parentElement={getAttribute:key=>key==='aria-hidden'?'true':null};
 assert.equal(f.c.xhsElementVisible(element),false);
 delete element.parentElement;assert.equal(f.c.xhsElementVisible(element),true);
});
test('RSS email verification is not mistaken for a security challenge, while real challenges still stop',()=>{
 const f=fixture();const doc={body:{innerText:'示例作者 添加RSS订阅 RSS地址 邮箱验证 验证码 获取邮箱验证码 本人已充分阅读、理解并接受 播客RSS导入服务协议'},querySelector:()=>null,querySelectorAll:()=>[]};
 const risk=()=>f.c.xhsPlatformRisk(doc,()=>true,e=>e.innerText||'');assert.equal(risk(),'');
 for(const label of ['安全验证','访问频繁','IP存在风险','扫码登录','短信登录']){doc.body.innerText=label;assert.match(risk(),new RegExp(label));}
 doc.body.innerText='验证码';doc.querySelectorAll=selector=>selector.includes('captcha-container')?[{innerText:'请输入图形验证码'}]:[];
 assert.match(risk(),/图形验证码/);
});
test('fixed test preparation rejects publication, arbitrary files, changed hashes and unrelated editor ownership',async()=>{
 const f=fixture(),base={fixture:'video',phase:'upload',title:'测试勿发布·功能调研',body:'这是创作者平台功能调研的独立测试稿'};
 const dependencies={visible:()=>true,text:e=>e?.innerText||'',check:()=>{},identity:()=>({})};
 await assert.rejects(()=>f.c.xhsCreatorFixture({...base,phase:'publish'},dependencies),/未开放/);
 await assert.rejects(()=>f.c.xhsCreatorFixture({...base,name:'private.mp4',mime:'video/mp4',data:'AA=='},dependencies),/文件无效/);
 await assert.rejects(()=>f.c.xhsCreatorFixture({...base,name:'creator-test.mp4',mime:'video/mp4',data:'AA==',sha256:'wrong'},dependencies),/哈希不符/);
 await assert.rejects(()=>f.c.xhsCreatorFixture({...base,phase:'save'},dependencies),/不属于/);
 assert.equal(f.clicks,0);
});
test('longform research keeps the paginated source distinct from the final short caption and refuses later edits',async()=>{
 const f=fixture();let template=false,clicked=0,pages=[];
 class Input {constructor(){this._value='';this.tagName='TEXTAREA';}get value(){return this._value;}set value(v){this._value=v;}dispatchEvent(){}}
 const title=new Input(),body={innerText:'',editor:{commands:{setContent(value){body.innerText=value.content.map(p=>p.content[0].text).join('\n\n');}},emit(){}}};
 f.c.HTMLTextAreaElement=Input;f.c.Event=Event;
 const next={innerText:'下一步',click(){clicked++;}};
 f.c.document.querySelectorAll=selector=>selector.startsWith('input[placeholder')?(template?[]:[title]):selector==='.tiptap.ProseMirror,.ql-editor'?(template?[pages[0]]:[body]):selector==='.tiptap.ProseMirror'?(template?pages:[body]):selector==='button,[role="button"]'?[next]:[];
 f.c.document.querySelector=()=>null;
 const deps={visible:e=>!!e,text:e=>e?.innerText?.trim()||'',check(){},identity:()=>({}),until:async fn=>fn()};
 const args={fixture:'longform',title:'测试勿发布·功能调研',body:'这是创作者平台功能调研的独立测试稿，不用于正式发布。'};
 await f.c.xhsCreatorFixture({...args,phase:'upload'},deps);
 await f.c.xhsCreatorFixture({...args,phase:'fill'},deps);
 const source=f.c.window.__xhsCreatorFixture.body;assert.match(source,/测试章节12/);assert.equal(body.innerText,source);
 const split=Math.floor(source.length/2);pages=[{innerText:source.slice(0,split)},{innerText:source.slice(split)}];
 template=true;f.c.document.body.innerText=args.title;f.c.window.__xhsCreatorFixture.phase='layout';
 await f.c.xhsCreatorFixture({...args,phase:'next'},deps);assert.equal(clicked,1);
 template=false;body.innerText='';
 await f.c.xhsCreatorFixture({...args,phase:'fill'},deps);assert.equal(body.innerText,args.body);assert.equal(f.c.window.__xhsCreatorFixture.body,source);
 await f.c.xhsCreatorFixture({...args,phase:'fill'},deps);assert.equal(body.innerText,args.body);
 title.value='人工修改';await assert.rejects(()=>f.c.xhsCreatorFixture({...args,phase:'save'},deps),/已改变/);assert.equal(clicked,1);
});
