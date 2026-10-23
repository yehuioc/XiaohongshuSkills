function xhsElementVisibility(element,allowEntering) {
  if(!element||!element.getClientRects().length)return false;
  for(let node=element;node;node=node.parentElement){
    if(node.getAttribute?.('aria-hidden')==='true'||node.hasAttribute?.('inert'))return false;
    if(typeof getComputedStyle==='function'){
      const style=getComputedStyle(node);
      if(style.visibility==='hidden'||style.display==='none')return false;
      if(parseFloat(style.opacity)<0.01){
        const entering=allowEntering&&typeof document!=='undefined'&&document.visibilityState==='hidden'&&
          typeof location!=='undefined'&&location.hostname==='creator.xiaohongshu.com'&&
          node.matches?.('.d-modal-mask.portal-fade-enter-from.portal-fade-enter-active,.d-popover.fade-in-enter-from.fade-in-enter-active');
        if(!entering)return false;
      }
    }
  }
  return true;
}
function xhsElementVisible(element){return xhsElementVisibility(element,false);}
function xhsCreatorLeaving(element){for(let node=element;node;node=node.parentElement)if(/(?:^|\s)[\w-]*-leave-(?:from|active|to)(?:\s|$)/.test(String(node.className||'')))return true;return false;}
function xhsCreatorElementAvailable(element){return !xhsCreatorLeaving(element)&&xhsElementVisibility(element,true);}

function xhsPlatformRisk(document,visible,text) {
  const challenge=[...document.querySelectorAll('.captcha-container,.verify-container')].filter(visible).map(text).join('\n');
  if(challenge&&/验证码|安全验证/.test(challenge))return challenge.slice(0,500);
  let box=[...document.querySelectorAll('[role="dialog"],.error-page,.error-wrapper,.login-container,.login-modal')].filter(visible).map(text).join('\n');
  const body=text(document.body);
  if(!document.querySelector('section.note-item,.note-detail-mask')&&body.length<2000)box+='\n'+body;
  // RSS importing contains legitimate email-code fields. A code mention alone
  // is not a challenge, login wall or platform rate limit.
  return /安全验证|访问频繁|IP存在风险|300012|300015|扫码登录|手机号登录|短信登录/.test(box)?box.slice(0,500):'';
}

// Dispatch one complete interaction at the real control, including release.
// A missing mouseup leaves Design-system controls in their pressing state.
function xhsCreatorClick(element,check) {
  const previous=window.__xhsCreatorSelect,wrapper=element.closest?.('.d-select-wrapper');
  if(!element.closest?.('.d-dropdown')){
    const others=new Set([previous,...document.querySelectorAll('.d-select-wrapper')]);
    for(const other of others)if(other&&other!==wrapper){check();other.dispatchEvent(new FocusEvent('focusout',{bubbles:true,relatedTarget:element}));other.blur?.();}
    window.__xhsCreatorSelect=wrapper||null;
  }
  element.scrollIntoView?.({block:'center',inline:'nearest'});
  const rect=element.getBoundingClientRect?.()||{left:0,top:0,width:0,height:0};
  const options={bubbles:true,cancelable:true,composed:true,button:0,clientX:rect.left+rect.width/2,clientY:rect.top+rect.height/2};
  for(const [name,buttons] of [['pointerover',0],['mouseover',0],['pointerdown',1],['mousedown',1],['pointerup',0],['mouseup',0],['click',0]]){
    // Select opens on focusin, not click. Synthetic mousedown has no default focus.
    if(name==='mousedown'){
      check();
      (wrapper||element).focus?.({preventScroll:true});
      // In a minimized/background document focus() need not dispatch focusin.
      if(wrapper){check();wrapper.dispatchEvent(new FocusEvent('focusin',{bubbles:true,composed:true}));}
    }
    check();const EventClass=name.startsWith('pointer')&&typeof PointerEvent==='function'?PointerEvent:MouseEvent;
    element.dispatchEvent(new EventClass(name,{...options,buttons,pointerId:1,pointerType:'mouse',isPrimary:true}));
  }
}

// Creator research deliberately excludes submit, edit, delete and settings writes.
function xhsCreatorResearch(action,args,{visible:hasBox,text,check,identity}) {
  if(location.hostname!=='creator.xiaohongshu.com')throw Error('请先在绑定页打开创作者平台');
  const visible=e=>xhsCreatorElementAvailable(e);
  const compact=value=>String(value||'').replace(/\s/g,'');
  const routes={notes:'笔记管理',publish_entry:'发布笔记',video:'上传视频',images:'上传图文',longform:'写长文',podcast:'发播客',drafts:'草稿箱',all:'全部',published:'已发布',reviewing:'审核中',rejected:'未通过',draft_video:'视频笔记',draft_images:'图文笔记',draft_longform:'长文笔记',draft_podcast:'播客笔记',draft_close:'关闭草稿箱',modal_close:'关闭检查弹窗',new_longform:'新的创作',import_link:'导入链接',rss:'添加RSS订阅',back:'返回'};
  const matches=(element,label)=>{
    const value=compact(text(element));
    return value===label || (['草稿箱','全部','视频笔记','图文笔记','长文笔记','播客笔记'].includes(label)&&new RegExp('^'+label+'[（(]?\\d+[）)]?$').test(value));
  };
  const candidates=label=>{
    // Creator duplicates tab text for its upload dropdown; note status badges
    // also reuse list filter names. Resolve the actual tab container first.
    const scoped=[...document.querySelectorAll('.creator-tab,.tab-list .tab-item')].filter(e=>visible(e)&&matches(e,label));
    if(scoped.length)return scoped;
    return [...document.querySelectorAll('button,a,[role="button"],[role="tab"],div,span')].filter(e=>visible(e)&&matches(e,label)&&![...e.children].some(child=>visible(child)&&matches(child,label)));
  };
  const dirty=()=>{
    // SPA keeps detached/hidden upload inputs after leaving the editor. Their
    // FileList must not make note-manager navigation look like an unsaved draft.
    if(location.pathname!=='/publish/publish')return false;
    const fields=[...document.querySelectorAll('input:not([type="hidden"]):not([type="file"]),textarea,[contenteditable="true"]')].filter(visible);
    const authored=fields.some(e=>!(/搜索/.test(e.getAttribute('placeholder')||''))&&Boolean((e.value||text(e)).trim()));
    const media=[...document.querySelectorAll('.img-preview-area img,.image-list img,.image-overview,.short-container [contenteditable="true"],video[src],audio[src]')].some(visible);
    const selected=[...document.querySelectorAll('input[type="file"]')].some(e=>e.files?.length&&(!e.closest('.d-modal')||visible(e.closest('.d-modal'))));
    return authored||media||selected;
  };
  const creatorNoteId=element=>{try{return JSON.parse(element.getAttribute('data-impression')).noteTarget.value.noteId||'';}catch(_){return '';}};
  const inspect=()=>{
    const elements=[...document.querySelectorAll('button,a,input,textarea,select,[role="button"],[role="tab"],[role="switch"],[role="checkbox"],[contenteditable="true"]')].filter(e=>visible(e)||e.type==='file');
    const marker=document.getElementById?.('xhs-research-workbench-marker');
    return {url:location.origin+location.pathname,observed_at:new Date().toISOString(),account:identity(),control_marker:marker?{text:text(marker),revision:marker.dataset.revision,instance:marker.dataset.instance}:null,test_fixture:window.__xhsCreatorFixture||null,text:text(document.body).slice(0,30000),text_truncated:text(document.body).length>30000,editor_has_content:dirty(),
      navigation:Object.entries(routes).map(([target,label])=>({target,label,matches:candidates(label).length})).filter(row=>row.matches),
      navigation_structure:[...document.querySelectorAll('.creator-tab,.tab-list .tab-item')].map(e=>({text:text(e),parent:e.parentElement?.outerHTML.slice(0,9000),display:getComputedStyle(e).display,visibility:getComputedStyle(e).visibility})).slice(0,15),
      panels:[...document.querySelectorAll('.d-drawer,.d-modal,[role="dialog"]')].filter(visible).map(e=>({classes:String(e.className||''),transition_pending:!xhsElementVisible(e),html:e.outerHTML.replace(/src="data:[^"]*"/g,'src="data:omitted"').slice(0,24000)})),
      overlay_controls:[...document.querySelectorAll('[class*="close"],[class*="dropdown"],[class*="cover-editor"]')].filter(visible).slice(-35).map(e=>({classes:String(e.className||''),text:text(e).slice(0,1400),html:e.outerHTML.replace(/<svg[\s\S]*?<\/svg>/g,'<svg/>').replace(/src="data:[^"]*"/g,'src="data:omitted"').slice(0,4500)})),
      upload_surfaces:[...document.querySelectorAll('.drag-text,.upload-input')].map(e=>({classes:String(e.className||''),html:e.parentElement?.parentElement?.outerHTML.slice(0,14000)})).slice(0,4),
      submit_controls:[...document.querySelectorAll('button,div,span')].filter(e=>['发布','暂存离开','存草稿','保存草稿','暂存草稿','下一步','完成'].includes(text(e))&&![...e.children].some(c=>text(c)===text(e))).slice(0,20).map(e=>({text:text(e),visible:visible(e),html:e.parentElement?.outerHTML.slice(0,7000)})),
      embedded_surfaces:[...document.querySelectorAll('iframe,wujie-app,micro-app')].map(e=>({tag:e.tagName,src:e.getAttribute('src'),classes:String(e.className||''),text:e.shadowRoot?.textContent?.slice(-1800)})),
      footer_structure:[...document.querySelectorAll('[class*="footer"],[class*="publish-btn"],[class*="submit-btn"]')].slice(-18).map(e=>({classes:String(e.className||''),html:e.outerHTML.slice(0,6000)})),
      action_structure:[...document.querySelectorAll('[class]')].filter(e=>/submit|save-|draft-|publish-page-(bottom|footer)|bottom-button|bottom-btn/.test(String(e.className||''))).slice(-25).map(e=>({classes:String(e.className||''),html:e.outerHTML.slice(0,3000)})),
      setting_structure:[...document.querySelectorAll('.d-select')].slice(0,12).map(e=>({text:text(e),html:e.outerHTML.slice(0,9000)})),
      interaction_surfaces:[...document.querySelectorAll('.d-select,.cover-plugin-title,.cover')].slice(0,16).map(e=>({classes:String(e.className||''),html:(e.parentElement?.outerHTML||e.outerHTML).replace(/<svg[\s\S]*?<\/svg>/g,'<svg/>').replace(/src="data:[^"]*"/g,'src="data:omitted"').slice(0,16000)})),
      script_assets:[...document.scripts||[]].map(e=>e.src).filter(Boolean).slice(0,40),
      shadow_surfaces:[...document.querySelectorAll('*')].filter(e=>e.shadowRoot).slice(0,10).map(e=>({tag:e.tagName,classes:String(e.className||''),text:e.shadowRoot.innerText||e.shadowRoot.textContent?.slice(-1000)})),
      controls:elements.slice(0,180).map(e=>({tag:e.tagName,role:e.getAttribute('role'),type:e.getAttribute('type'),visible:visible(e),text:text(e).slice(0,250),title:e.getAttribute('title'),aria_label:e.getAttribute('aria-label'),html:e.tagName==='BUTTON'?e.outerHTML?.slice(0,1600):undefined,placeholder:e.getAttribute('placeholder'),value:['password','file','hidden'].includes(e.type)?undefined:(e.value||'').slice(0,1200),accept:e.getAttribute('accept'),maxlength:e.getAttribute('maxlength'),min:e.getAttribute('min'),max:e.getAttribute('max'),expanded:e.getAttribute('aria-expanded'),multiple:e.hasAttribute('multiple'),disabled:!!e.disabled||e.getAttribute('aria-disabled')==='true',checked:e.getAttribute('aria-checked')??(typeof e.checked==='boolean'?e.checked:undefined),classes:String(e.className||'').slice(0,180)})),
      labels:[...document.querySelectorAll('div,span,label')].filter(e=>visible(e)&&text(e)&&text(e).length<=100&&![...e.children].some(child=>visible(child)&&text(child))).slice(0,300).map(e=>({text:text(e),classes:String(e.className||'').slice(0,180),parent_classes:String(e.parentElement?.className||'').slice(0,180)})),
      list_filter:text(document.querySelector('.tab-list .tab-item--active')),
      creator_settings:[...document.querySelectorAll('.d-select-wrapper')].filter(visible).map(e=>({classes:String(e.className||''),value:text(e)})),
      preview_editor_structure:[...document.querySelectorAll('button,div,span')].filter(e=>visible(e)&&text(e)==='完成'&&![...e.children].some(c=>text(c)==='完成')).slice(-3).map(e=>({html:e.parentElement?.parentElement?.parentElement?.outerHTML.replace(/<svg[\s\S]*?<\/svg>/g,'<svg/>').replace(/src="data:[^"]*"/g,'src="data:omitted"').slice(0,18000)})),
      transition_surfaces:[...document.querySelectorAll('button,div,span')].filter(e=>text(e)==='完成'&&![...e.children].some(c=>text(c)==='完成')).slice(-2).map(e=>{const chain=[];for(let n=e;n&&chain.length<16;n=n.parentElement){const s=getComputedStyle(n);chain.push({classes:String(n.className||''),display:s.display,opacity:s.opacity,visibility:s.visibility,rects:n.getClientRects().length,html:chain.length===8?n.outerHTML.replace(/<svg[\s\S]*?<\/svg>/g,'<svg/>').replace(/src="data:[^"]*"/g,'src="data:omitted"').slice(0,11000):undefined});}return chain;}),
      list_total:(()=>{const tab=[...document.querySelectorAll('.tab-list .tab-item')].find(e=>/^全部/.test(compact(text(e))));const match=compact(text(tab)).match(/^全部[（(]?(\d+)/);return match?Number(match[1]):null;})(),
      note_cards:[...document.querySelectorAll('.note-card')].slice(0,200).map(e=>({note_id:creatorNoteId(e),title:text(e.querySelector('.note-card__title')),time:text(e.querySelector('.note-card__time')),tags:[...e.querySelectorAll('.note-card__tag')].map(text),metrics:[...e.querySelectorAll('.note-card__stat')].map(text),actions:[...e.querySelectorAll('.note-card__action-btn')].map((a,index)=>({index,visible:visible(a),title:a.getAttribute('title'),aria_label:a.getAttribute('aria-label'),classes:String(a.className||'')})),text:text(e),html:e.outerHTML.slice(0,16000)})),
      drafts:[...document.querySelectorAll('.draft-item[data-draft-id]')].map(e=>({id:e.getAttribute('data-draft-id'),type:e.getAttribute('data-draft-type'),title:text(e.querySelector('.draft-title-text')),saved_at:text(e.querySelector('.draft-time'))})),
      scroll_regions:[...document.querySelectorAll('main,section,div')].filter(e=>visible(e)&&e.scrollHeight>e.clientHeight+1&&/auto|scroll/.test(getComputedStyle(e).overflowY)).slice(0,15).map(e=>({classes:String(e.className||''),top:e.scrollTop,height:e.clientHeight,total:e.scrollHeight})),
      list_ancestors:(()=>{const out=[];for(let e=document.querySelector('.note-card');e&&out.length<9;e=e.parentElement)out.push({tag:e.tagName,classes:String(e.className||''),height:e.clientHeight,total:e.scrollHeight,top:e.scrollTop,overflow:getComputedStyle(e).overflowY,rect:{top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom}});return out;})(),
      structure:[...document.querySelectorAll('main,section,article,[role="dialog"],form')].filter(visible).slice(0,30).map(e=>({tag:e.tagName,role:e.getAttribute('role'),classes:String(e.className||'').slice(0,180),text:text(e).slice(0,1500)})),scope:'当前已加载页面；不代表所有笔记、草稿或隐藏设置；只检查，不提交'};
  };
  if(action==='creator_inspect')return inspect();
  if(action==='creator_navigate'&&args.target==='resume_test'){
    if(dirty()||!(/^[a-f0-9-]{36}$/.test(args.draft_id||'')))throw Error('只允许从草稿箱定位指定测试稿，当前不得有编辑内容');
    const rows=[...document.querySelectorAll('.draft-item[data-draft-id]')].filter(e=>e.getAttribute('data-draft-id')===args.draft_id&&visible(e));
    const row=rows[0];
    if(rows.length!==1||text(row.querySelector('.draft-title-text'))!=='测试勿发布·功能调研')throw Error('不是已指定的调研测试稿，未打开');
    const buttons=[...row.querySelectorAll('.draft-actions .btn')].filter(e=>text(e)==='编辑'&&visible(e));
    if(buttons.length!==1)throw Error('测试草稿编辑入口不唯一');
    check();window.__xhsCreatorResume={id:args.draft_id,type:row.getAttribute('data-draft-type')};buttons[0].click();
    return {opened_test_draft:args.draft_id,published:false,message:'只打开指定的测试草稿；恢复前仍须核对完整标题与正文'};
  }
  if(action==='creator_navigate'&&args.target==='note_search'){
    if(location.pathname!=='/new/note-manager'||typeof args.keyword!=='string'||args.keyword.length>100)throw Error('仅支持在笔记管理页检索，关键词最多100字');
    const inputs=[...document.querySelectorAll('input[placeholder="搜索已发布的笔记"]')].filter(visible);
    if(inputs.length!==1)throw Error('笔记搜索框不存在或不唯一');
    check();const input=inputs[0];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,args.keyword);
    input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
    return {searched:true,keyword:args.keyword,published:false,message:'已输入查询；另行检查实际结果，不修改笔记'};
  }
  if(action==='creator_navigate'&&['note_action_hint','note_permissions'].includes(args.target)){
    if(location.pathname!=='/new/note-manager'||!(/^[a-f0-9]{24}$/.test(args.note_id||'')))throw Error('请先定位笔记管理中的具体笔记');
    const card=[...document.querySelectorAll('.note-card')].find(e=>creatorNoteId(e)===args.note_id);
    const buttons=card?[...card.querySelectorAll('.note-card__action-btn')]:[];
    if(args.target==='note_permissions'){
      if(window.__xhsCreatorHover!==buttons[0]||!text(document.body).endsWith('权限设置'))throw Error('请先核对该笔记权限入口的实际提示');
      check();buttons[0].click();return {clicked:true,note_id:args.note_id,published:false,message:'仅展开权限菜单，不选择或修改可见范围'};
    }
    if(!Number.isInteger(args.index)||args.index<0||args.index>=buttons.length)throw Error('笔记操作检查序号无效');
    check();window.__xhsCreatorHover?.dispatchEvent(new MouseEvent('mouseleave',{bubbles:true}));
    const button=buttons[args.index];button.dispatchEvent(new MouseEvent('mouseenter',{bubbles:true}));button.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));window.__xhsCreatorHover=button;
    return {hovered:true,note_id:args.note_id,index:args.index,clicked:false,published:false};
  }
  if(action==='creator_navigate'&&args.target==='toolbar_hint'){
    const buttons=[...document.querySelectorAll('button.menu-item')].filter(visible);
    if(!Number.isInteger(args.index)||args.index<0||args.index>=buttons.length)throw Error('工具栏检查序号无效');
    const previous=window.__xhsCreatorHover;
    check();previous?.dispatchEvent(new MouseEvent('mouseleave',{bubbles:true}));
    const button=buttons[args.index];button.dispatchEvent(new MouseEvent('mouseenter',{bubbles:true}));button.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));window.__xhsCreatorHover=button;
    return {hovered:true,index:args.index,clicked:false,published:false};
  }
  if(action!=='creator_navigate'||!Object.prototype.hasOwnProperty.call(routes,args.target))throw Error('未开放此创作者导航目标');
  if(dirty())throw Error('编辑器已有内容或原生写作区，未导航；请先人工保存，不覆盖草稿');
  const draftPanel=document.querySelector('.draft-drawer');
  if(visible(draftPanel)&&!args.target.startsWith('draft_'))throw Error('请先关闭草稿箱，再切换后台页面');
  const modal=[...document.querySelectorAll('.d-modal')].find(visible);
  if(modal&&args.target!=='modal_close')throw Error('请先关闭检查弹窗，再切换后台页面');
  const choices=args.target==='draft_close'?[...document.querySelectorAll('.draft-drawer .d-drawer-close')].filter(visible):args.target==='modal_close'?[...document.querySelectorAll('.d-modal .d-modal-close')].filter(visible):candidates(routes[args.target]);
  if(choices.length!==1)throw Error('导航入口不存在或不唯一，未点击：'+routes[args.target]);
  const leaf=choices[0],target=leaf.closest('button,a,[role="button"],[role="tab"],.creator-tab')||leaf;
  const href=target.getAttribute('href');
  if(href){const url=new URL(href,location.href);if(url.origin!==location.origin||/delete|remove|logout|submit/i.test(url.pathname))throw Error('链接超出创作者调研范围，未点击');}
  if(target.disabled||target.getAttribute('aria-disabled')==='true')throw Error('导航入口不可用，未点击');
  const before=location.origin+location.pathname;
  check();target.click();
  return {requested:args.target,clicked:true,before,published:false,message:'仅已点击导航入口；须再次 creator_inspect 核对加载后的实际页面，不能把点击当作到达'};
}

// Authorized research uses fixed, visibly marked test content, never user files
// or a general-purpose write/click RPC. Publication is deliberately absent.
async function xhsCreatorFixture(args,{visible:hasBox,text,check,until,identity}) {
  const visible=e=>!xhsCreatorLeaving(e)&&(hasBox(e)||xhsCreatorElementAvailable(e));
  if(location.hostname!=='creator.xiaohongshu.com')throw Error('测试稿仅支持创作者平台');
  if(!['image','video','audio','longform'].includes(args.fixture)||args.title!=='测试勿发布·功能调研'||!args.body?.startsWith('这是创作者平台功能调研的独立测试稿'))throw Error('不是固定调研测试稿');
  if(!['upload','resume','fill','save','layout','next','cover','visibility','visibility_self','visibility_public','declaration','declaration_ai','declaration_clear','collection','preview_cover','dismiss','chapters','video_cover','close_modal','cover_crop','cover_templates','cover_stickers','cover_text','cover_filters'].includes(args.phase))throw Error('未开放此测试阶段');
  const shortBody=args.body;
  if(args.fixture==='longform')args={...args,body:Array.from({length:12},(_,i)=>'测试章节'+(i+1)+'\n\n'+args.body).join('\n\n')};
  const same=(a,b)=>String(a||'').replace(/\s/g,'')===String(b||'').replace(/\s/g,'');
  const fields=()=>({title:[...document.querySelectorAll('input[placeholder*="标题"],textarea[placeholder*="标题"]')].find(visible),body:[...document.querySelectorAll('.tiptap.ProseMirror,.ql-editor')].find(visible)});
  const button=labels=>[...document.querySelectorAll('button,[role="button"]')].filter(e=>visible(e)&&labels.includes(text(e)));
  const current=fields();
  if(args.phase==='resume'){
    const pending=window.__xhsCreatorResume,expected={image:'image',video:'video',audio:'audio',longform:'article'}[args.fixture];
    if(!pending||pending.type!==expected||current.title?.value!==args.title||!same(text(current.body),shortBody))throw Error('测试稿ID、类型、完整标题或正文不一致，未恢复');
    check();window.__xhsCreatorFixture={fixture:args.fixture,title:args.title,body:args.body,caption:shortBody,phase:'filled',draft_id:pending.id};
    delete window.__xhsCreatorResume;
    return {resumed:true,draft_id:pending.id,published:false};
  }
  if(args.phase==='upload'){
    if(window.__xhsCreatorFixture?.phase==='save'&&!current.title?.value&&!text(current.body)&&!document.querySelector('.img-preview-area img,video[src],audio[src]'))delete window.__xhsCreatorFixture;
    if(window.__xhsCreatorFixture)throw Error('本页已有测试操作记录，未重放上传；先检查现状');
    if(current.title?.value||text(current.body)||document.querySelector('.img-preview-area img,video[src],audio[src]'))throw Error('编辑器已有内容，未覆盖');
    if(args.fixture==='longform'){
      if(!current.title||!current.body)throw Error('请先打开空白长文编辑器');
      window.__xhsCreatorFixture={fixture:args.fixture,title:args.title,body:args.body,phase:'selected'};
    }else{
      const expected={image:['creator-test.png','image/png'],video:['creator-test.mp4','video/mp4'],audio:['creator-test.mp3','audio/mpeg']}[args.fixture];
      if(args.name!==expected[0]||args.mime!==expected[1]||typeof args.data!=='string'||args.data.length>6000000)throw Error('调研测试文件无效');
      const bytes=Uint8Array.from(atob(args.data),c=>c.charCodeAt(0));
      const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
      if(hash!==args.sha256)throw Error('测试文件传输哈希不符，未上传');
      const transfer=new DataTransfer();transfer.items.add(new File([bytes],args.name,{type:args.mime}));
      const files=[...document.querySelectorAll('input[type="file"]')].filter(e=>(e.accept||'').split(',').some(a=>a.trim().toLowerCase()==='.'+args.name.split('.').pop()));
      if(files.some(e=>e.files?.length))throw Error('页面已选择文件，未覆盖');
      const drop=args.fixture==='audio'?[...document.querySelectorAll('.drag-text')].find(e=>visible(e)&&text(e).includes('音频文件'))?.closest('.wrapper'):null;
      if(files.length!==1&&!drop)throw Error('未找到唯一测试上传入口，未上传');
      check();window.__xhsCreatorFixture={fixture:args.fixture,title:args.title,body:args.body,sha256:hash,phase:'selected'};
      if(files.length===1){files[0].files=transfer.files;files[0].dispatchEvent(new Event('change',{bubbles:true}));}
      else drop.dispatchEvent(new DragEvent('drop',{dataTransfer:transfer,bubbles:true,cancelable:true}));
    }
    return {selected:true,published:false,message:'测试素材只选择一次；另行检查上传和编辑器状态'};
  }
  const record=window.__xhsCreatorFixture;
  const audioCover=args.phase==='cover'&&args.fixture==='image'&&record?.fixture==='audio';
  if(!record||(!audioCover&&record.fixture!==args.fixture)||record.title!==args.title||record.body!==args.body)throw Error('当前编辑器不属于这份固定测试稿，未修改');
  if(audioCover){
    if(record.cover_sha256)throw Error('测试封面已选择，未重放');
    if(args.name!=='creator-test.png'||args.mime!=='image/png'||typeof args.data!=='string'||args.data.length>100000)throw Error('不是固定测试封面');
    const bytes=Uint8Array.from(atob(args.data),c=>c.charCodeAt(0));
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
    if(hash!==args.sha256)throw Error('测试封面哈希不符');
    const files=[...document.querySelectorAll('input[type="file"]')].filter(e=>(e.accept||'').includes('.png'));
    if(files.length!==1||files[0].files?.length)throw Error('测试封面入口不唯一或已有文件');
    const transfer=new DataTransfer();transfer.items.add(new File([bytes],args.name,{type:args.mime}));
    check();record.cover_sha256=hash;files[0].files=transfer.files;files[0].dispatchEvent(new Event('change',{bubbles:true}));
    return {selected:true,published:false,message:'测试封面已选择一次，须检查实际预览'};
  }
  if(args.phase==='next'&&args.fixture==='audio'&&!current.title&&!current.body){
    const modal=[...document.querySelectorAll('.d-modal')].find(e=>visible(e)&&text(e).includes('音频封面')&&text(e).includes('creator-test.mp3')&&text(e).includes('上传成功'));
    const next=modal?[...modal.querySelectorAll('button')].filter(e=>visible(e)&&text(e)==='去发布'&&!e.disabled):[];
    if(next.length!==1||!record.cover_sha256)throw Error('测试音频和封面尚未全部就绪，未进入编辑器');
    check();record.phase='next';next[0].click();return {clicked:true,published:false,message:'仅从音频上传弹窗进入编辑器，未提交发布'};
  }
  if(args.fixture==='longform'&&record.phase==='layout'&&['next','save'].includes(args.phase)){
    const pages=[...document.querySelectorAll('.tiptap.ProseMirror')].filter(visible).map(text).join('');
    if(!same(pages,args.body)||!text(document.body).replace(/\s/g,'').includes(args.title))throw Error('长文分页内容或标题与测试稿不符，未继续');
    const choices=button(args.phase==='save'?['暂存离开']:['下一步']);
    if(choices.length!==1||choices[0].disabled)throw Error('长文模板页尚未就绪');
    check();record.phase=args.phase;choices[0].click();return {clicked:true,phase:args.phase,published:false,message:'已核对本轮长文全部分页，只进入下一阶段或存草稿'};
  }
  if(args.phase==='fill'){
    const ready=await until(()=>{const f=fields();return f.title&&f.body?f:false;},25000,'测试素材已选择，编辑器尚未就绪；不重放上传');
    if(ready.blocked)return ready;
    const writingBody=args.fixture==='longform'&&(record.phase==='next'||(record.caption&&record.caption!==record.body))?shortBody:args.body;
    const audioFilenameDefault=args.fixture==='audio'&&record.phase==='next'&&ready.title.value==='creator-test'&&!text(ready.body);
    if((ready.title.value&&!same(ready.title.value,args.title)&&!audioFilenameDefault)||(text(ready.body)&&!same(text(ready.body),writingBody)))throw Error('测试稿出现其他文字，未覆盖');
    check();const proto=ready.title.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(ready.title,args.title);ready.title.dispatchEvent(new Event('input',{bubbles:true}));
    if(!ready.body.editor?.commands?.setContent)throw Error('未确认正文编辑器接口，未写入');
    ready.body.editor.commands.setContent({type:'doc',content:writingBody.split(/\n\s*\n/).map(t=>({type:'paragraph',content:[{type:'text',text:t}]}))},true);
    ready.body.editor.emit?.('update',{editor:ready.body.editor});
    if(!same(ready.title.value,args.title)||!same(text(ready.body),writingBody))throw Error('测试稿文字未通过核对');
    record.caption=writingBody;record.phase='filled';return {filled:true,published:false,account:identity()};
  }
  if(!same(current.title?.value,args.title)||!same(text(current.body),record.caption||args.body))throw Error('当前测试稿已改变，未点击后续操作');
  const coverTabs={cover_crop:'裁剪',cover_templates:'模版',cover_stickers:'贴纸',cover_text:'文字',cover_filters:'滤镜'};
  if(Object.prototype.hasOwnProperty.call(coverTabs,args.phase)){
    const modal=document.querySelector('.main-cover-editor-modal');
    if(!visible(modal))throw Error('本轮封面编辑器尚未打开');
    const targets=[...modal.querySelectorAll('.category .item')].filter(e=>visible(e)&&text(e)===coverTabs[args.phase]);
    if(targets.length!==1)throw Error('封面工具标签不存在或不唯一');
    xhsCreatorClick(targets[0],check);
    await until(()=>targets[0].classList.contains('active'),6000,'封面工具未切换完成');
    return {cover_tab:coverTabs[args.phase],verified:true,published:false};
  }
  if(visible(document.querySelector('.main-cover-editor-modal'))&&!['close_modal','dismiss'].includes(args.phase))throw Error('请先关闭本轮封面编辑器，未操作遮罩下的页面');
  if(args.phase==='declaration_clear'){
    const wrapper=document.querySelector('.d-select-wrapper[lass="declaration-wrapper"]');
    if(!visible(wrapper))throw Error('未找到本轮测试稿内容声明');
    if(text(wrapper)==='添加内容类型声明')return {setting:'declaration',value:'',verified:true,published:false};
    if(text(wrapper)!=='笔记含AI合成内容')throw Error('不是本轮测试的声明值，未清除');
    xhsCreatorClick(wrapper.querySelector('.d-select-main'),check);
    await until(()=>visible(wrapper.querySelector('.d-select-suffix-clear')),6000,'未找到原生清除声明入口');
    xhsCreatorClick(wrapper.querySelector('.d-select-suffix-clear'),check);
    await until(()=>text(wrapper)==='添加内容类型声明',6000,'声明清除后未回读一致');
    return {setting:'declaration',value:'',verified:true,published:false};
  }
  if(['visibility_self','visibility_public','declaration_ai'].includes(args.phase)){
    const isVisibility=args.phase.startsWith('visibility_');
    const wrapper=document.querySelector(isVisibility?'.permission-card-select':'.d-select-wrapper[lass="declaration-wrapper"]');
    const opener=wrapper?.querySelector('.d-select-main');
    if(!visible(opener))throw Error('本轮测试稿设置入口不存在');
    xhsCreatorClick(opener,check);
    const label=args.phase==='visibility_self'?'仅自己可见':args.phase==='visibility_public'?'公开可见':'笔记含AI合成内容';
    const choices=()=>[...document.querySelectorAll('.d-dropdown .custom-option,.d-dropdown .d-option-content')].filter(e=>visible(e)&&text(e)===label);
    await until(()=>choices().length===1,6000,'未读到唯一设置选项，未选择');
    xhsCreatorClick(choices()[0],check);
    await until(()=>text(wrapper).includes(label),6000,'设置值未回读一致，未继续');
    return {setting:isVisibility?'visibility':'declaration',value:label,verified:true,published:false};
  }
  if(['visibility','declaration','collection','preview_cover','dismiss','chapters','video_cover','close_modal'].includes(args.phase)){
    const labels={visibility:'公开可见',declaration:'添加内容类型声明',collection:'选择合集',preview_cover:'封面预览',dismiss:'取消',chapters:'添加章节',video_cover:'设置封面',close_modal:'关闭调研弹窗'};
    const label=labels[args.phase];
    const selectOpener=args.phase==='visibility'?'.permission-card-select .d-select-main':args.phase==='declaration'?'.d-select-wrapper[lass="declaration-wrapper"] .d-select-main':null;
    const matches=selectOpener?[...document.querySelectorAll(selectOpener)].filter(visible):args.phase==='chapters'?[...document.querySelectorAll('.add-chapter-btn')].filter(visible):args.phase==='video_cover'?[...document.querySelectorAll('.cover-plugin-preview .cover-edit-entry')].filter(e=>visible(e.closest('.cover-plugin-preview'))):args.phase==='close_modal'?[...document.querySelectorAll('.main-cover-editor-modal .close-icon,.d-modal .d-modal-close')].filter(visible):[...document.querySelectorAll('button,div,span')].filter(e=>visible(e)&&text(e)===label&&![...e.children].some(c=>text(c)===label));
    if(matches.length!==1)throw Error('测试稿检查入口不存在或不唯一');
    const opener=matches[0].closest('.d-select-main,button,.button-switch-item,.collection-plugin-button')||matches[0];
    xhsCreatorClick(opener,check);
    if(args.phase==='visibility'||args.phase==='declaration'){
      const label=args.phase==='visibility'?'仅自己可见':'笔记含AI合成内容';
      const options=()=>[...document.querySelectorAll('.d-popover.d-dropdown')].filter(e=>visible(e)&&text(e).includes(label));
      await until(()=>options().length===1,6000,'下拉未挂载完整选项，未继续');
      return {opened:true,requested:args.phase,options:text(options()[0]).split('\n'),transition_pending:!xhsElementVisible(options()[0]),published:false};
    }
    if(args.phase==='video_cover'){
      await until(()=>visible(document.querySelector('.main-cover-editor-modal .mojito-container')),12000,'封面编辑器未挂载，未继续');
      return {opened:true,requested:args.phase,transition_pending:!xhsElementVisible(document.querySelector('.main-cover-editor-modal')),published:false};
    }
    if(args.phase==='close_modal'){
      await until(()=>![...document.querySelectorAll('.d-modal')].some(visible),6000,'检查弹窗尚未关闭');
      return {closed:true,published:false};
    }
    return {requested:args.phase,event_sent:true,published:false,message:'只发送设置展开操作，须另行核对菜单出现；未选择值或提交'};
  }
  const labels=args.phase==='save'?['暂存离开','保存草稿','存草稿','暂存草稿']:args.phase==='layout'&&args.fixture==='longform'?['一键排版']:args.phase==='next'?['下一步']:[];
  const choices=button(labels);
  if(args.phase==='save'&&!choices.length){
    const notes=[...document.querySelectorAll('.menu-title-wrapper')].filter(e=>visible(e)&&text(e)==='笔记管理');
    if(notes.length!==1)throw Error('未找到存稿或离开测试稿入口');
    check();record.phase='save';notes[0].click();return {leave_requested:true,published:false,message:'已请求离开本轮测试稿；必须检查平台存稿提示及草稿箱，尚不能声明保存成功'};
  }
  if(choices.length!==1||choices[0].disabled)throw Error('未找到唯一的测试稿后续入口');
  check();record.phase=args.phase;choices[0].click();
  return {clicked:true,phase:args.phase,published:false,message:'只执行测试稿的保存或预览阶段；须检查实际结果'};
}

// Fixed, site-specific actions only. No model-supplied JavaScript or selectors.
async function xhsPageAction(action, args, context = {}) {
  const id = context.id || String(Math.random()), abort = new AbortController();
  const runs = window.__xhsResearchActions ||= {};
  runs[id] = {abort, inspect: null};
  const check = () => {
    if (abort.signal.aborted) throw Error('操作已停止');
    if (context.expires && Date.now() / 1000 >= context.expires) throw Error('操作已过期，未继续执行');
  };
  try {check(); return await xhsRunAction(action, args, check, abort.signal, inspect => {if(runs[id])runs[id].inspect=inspect;});}
  catch(e){if(e.platform_blocked)return {blocked:e.platform_blocked};return {adapter_error:String(e.message||e),adapter_recoverable:['native_entry','creator_inspect','creator_navigate','creator_fixture'].includes(action)};}
  finally {if (runs[id]?.abort === abort) delete runs[id];}
}
async function xhsRunAction(action, args, check = () => {}, signal, setInspector = () => {}) {
  const visible = xhsElementVisible;
  const text = e => e?.innerText?.trim() || '';
  const noteId = value => String(value || '').match(/\/(?:explore|search_result)\/([a-f0-9]{24})/)?.[1];
  // Observe DOM readiness directly: hidden-page timers can be heavily throttled.
  const until = (predicate, timeout, failure) => new Promise((resolve, reject) => {
    let observer, timer;
    const done = (error, value) => {setInspector(null); observer?.disconnect(); clearTimeout(timer); signal?.removeEventListener('abort', inspect); error ? reject(error) : resolve(value);};
    const inspect = () => {try {check(); if(risk()) return done(null, {blocked:risk()}); const value = predicate(); if(value) done(null, value);} catch(e) {done(e);}};
    observer = new MutationObserver(inspect); observer.observe(document.documentElement, {subtree:true,childList:true,attributes:true,characterData:true});
    timer = setTimeout(() => done(Error(failure)), timeout);
    signal?.addEventListener('abort', inspect, {once:true}); setInspector(inspect); inspect();
  });
  const risk = () => xhsPlatformRisk(document,visible,text);
  // List cards seed noteDetailMap with title/cover only. A visible modal and
  // matching URL are not proof that the detail response has arrived.
  const detailReady = id => {
    const record = window.__INITIAL_STATE__?.note?.noteDetailMap?.[id];
    const note = record?.note || record;
    return !!note && note.noteId === id && ['desc', 'time', 'interactInfo'].every(key => Object.prototype.hasOwnProperty.call(note, key));
  };
  if (!['www.xiaohongshu.com','creator.xiaohongshu.com'].includes(location.hostname)) throw Error('绑定标签页已离开小红书');
  if(risk())return {blocked:risk()};
  const identity = () => {
    const state=window.__INITIAL_STATE__ || {};
    let user=state.user?.userInfo || state.user?.user || {};
    const stored=[];
    if(location.hostname==='creator.xiaohongshu.com'){
      // Read only the creator's own user-info records, never auth tokens/cookies.
      for(const key of ['USER_INFO','USER_INFO_FOR_BIZ','snsWebPublishCurrentUser']){
        try{const value=JSON.parse(localStorage.getItem(key)||'null');if(!value||typeof value!=='object')continue;
          const candidates=[value,value.userInfo,value.user_info,value.data].filter(v=>v&&typeof v==='object');
          for(const entry of candidates){const id=String(entry.userId||entry.user_id||entry.userID||entry._id||entry.id||'');
            if(/^[a-f0-9]{24}$/.test(id))stored.push({userId:id,nickname:String(entry.nickname||entry.nickName||entry.name||''),record:key});
          }
        }catch(e){}
      }
      if(new Set(stored.map(entry=>entry.userId)).size>1)throw Error('创作者账号缓存存在冲突，未继续操作，请核对登录');
      if(stored.length)user=stored[0];
    }
    const self=[...document.querySelectorAll('a[href*="/user/profile/"]')].find(e=>text(e)==='我');
    return {user_id:String(user.userId||user.user_id||self?.href.match(/\/user\/profile\/([a-f0-9]{24})/)?.[1]||''),nickname:String(user.nickname||user.nickName||text(document.querySelector('.user-info'))||''),url:location.origin+location.pathname,
      verification:location.hostname==='creator.xiaohongshu.com'?'creator_user_info':self?'self_profile_link':'page_state'};
  };
  if(action==='identity')return identity();
  if(action==='creator_fixture')return xhsCreatorFixture(args,{visible,text,check,until,identity});
  if(['creator_inspect','creator_navigate'].includes(action))return xhsCreatorResearch(action,args,{visible,text,check,identity});
  if(action==='native_entry')return xhsNativePreview(args, {visible,text,check,until,identity});
  if(action==='preview_status'){
    if(location.hostname!=='creator.xiaohongshu.com')throw Error('当前页不是创作者编辑器');
    const title=document.querySelector('input[placeholder*="填写标题"],input[placeholder*="标题"],div.d-input input');
    const body=document.querySelector('div.tiptap.ProseMirror,div.ProseMirror[contenteditable="true"],div.ql-editor');
    return {native_context:{trace:window.__xhsNativeTrace||[],layout:[...document.querySelectorAll('.image-editor-container,.short-container')].slice(0,1).map(e=>e.outerHTML.slice(0,22000)),controls:[...document.querySelectorAll('button,a,div,span')].filter(e=>visible(e)&&['返回','上传图文','文字配图','生成图片','下一步','完成','使用','发布'].includes(text(e))&&![...e.children].some(c=>text(c)===text(e))).map(e=>{const rows=[];for(let n=e,i=0;n&&i<8;n=n.parentElement,i++)rows.push({tag:n.tagName,cls:n.className,role:n.getAttribute('role'),disabled:n.getAttribute('disabled'),text:text(n).slice(0,150)});return rows;}).slice(0,4),text:text(document.body).slice(0,8000),editables:[...document.querySelectorAll('textarea,input:not([type=hidden]),[contenteditable=true]')].filter(visible).map(e=>({editor_state:{hasView:!!e.editor?.view,modelText:e.editor?.state?.doc?.textContent,modelJSON:e.editor?.state?.doc?.toJSON?.()},html:e.outerHTML.slice(0,1500),tag:e.tagName,placeholder:e.getAttribute('placeholder'),role:e.getAttribute('role'),value:e.value||text(e)})).slice(0,12)},title:title?.value||'',body:text(body),image_count:document.querySelectorAll('.img-preview-area .pr').length,
      uploading:/上传中|正在上传/.test(text(document.body)),upload_failed:/上传失败|图片上传失败/.test(text(document.body)),account:identity()};
  }
  if(action==='preview'){
    if(location.hostname!=='creator.xiaohongshu.com')throw Error('请在绑定标签页打开创作者中心的图文发布页，再填写预览');
    const input=document.querySelector('input[placeholder*="填写标题"],input[placeholder*="标题"],div.d-input input');
    const editor=document.querySelector('div.tiptap.ProseMirror,div.ProseMirror[contenteditable="true"],div.ql-editor');
    let upload=[...document.querySelectorAll('input[type="file"]')].find(e=>/image|\.(?:jpg|jpeg|png|webp)/i.test(e.accept||''));
    if(text(editor)||input?.value?.trim()||document.querySelector('.img-preview-area img,.image-list img')||[...document.querySelectorAll('input[type="file"]')].some(e=>e.files?.length))throw Error('编辑器已有内容，请先人工保存或清空；不会覆盖现有草稿');
    if(!upload){
      const tab=[...document.querySelectorAll('.creator-tab')].find(e=>visible(e)&&text(e)==='上传图文');
      if(!tab)throw Error('未找到图文上传入口，本次未上传');
      check(); tab.click();
      const ready = await until(() => [...document.querySelectorAll('input[type="file"]')].find(e=>/image|\.(?:jpg|jpeg|png|webp)/i.test(e.accept||'')), 6000, '图文上传区未就绪');
      if(ready.blocked)return ready; upload=ready;
    }
    if(!upload)throw Error('图文上传区未就绪；本次未选择文件或点击发布');
    const transfer=new DataTransfer();
    for(let i=0;i<args.images.length;i++){const binary=atob(args.images[i]);const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));transfer.items.add(new File([bytes],String(i+1).padStart(2,'0')+'.png',{type:'image/png'}));}
    check(); upload.files=transfer.files;upload.dispatchEvent(new Event('change',{bubbles:true}));
    const ready = await until(() => document.querySelector('input[placeholder*="标题"],div.d-input input')&&document.querySelector('div.ProseMirror,div.ql-editor'), 15000, '图片已选择，但编辑器未就绪；请人工核对，未自动重试上传');
    if(ready.blocked)return ready;
    const title=document.querySelector('input[placeholder*="填写标题"],input[placeholder*="标题"],div.d-input input');
    const body=document.querySelector('div.tiptap.ProseMirror,div.ProseMirror[contenteditable="true"],div.ql-editor');
    if(!title||!body)throw Error('图片已选择，但编辑器未就绪；请人工核对，未自动重试上传');
    check(); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(title,args.title);title.dispatchEvent(new Event('input',{bubbles:true}));
    body.focus();document.execCommand('insertText',false,args.body);body.dispatchEvent(new Event('input',{bubbles:true}));
    if(title.value!==args.title||!text(body).includes(args.body.split('\n')[0]))throw Error('预览文字未能核对，请人工检查');
    return {message:'图片已选择、标题和正文已填写。请逐页核对上传完成、顺序与话题；正式发布由你在 Chrome 点击。',draft_id:args.draft_id,revision:args.revision,upload_selected:args.images.length,published:false};
  }
  if(action==='snapshot'){
    const cards=[];const seen=new Set();
    for(const card of document.querySelectorAll('section.note-item,.note-item')){
      if(!visible(card))continue;
      const link=[...card.querySelectorAll('a[href]')].find(e=>noteId(e.href));
      const id=noteId(link?.href);if(!id||seen.has(id))continue;seen.add(id);
      cards.push({note_id:id,title:text(card.querySelector('.title'))||text(card).slice(0,150),author:text(card.querySelector('.author-wrapper,.author')).split('\n')[0],url:'https://www.xiaohongshu.com/explore/'+id});
      if(cards.length>=30)break;
    }
    return {cards,keyword:new URL(location.href).searchParams.get('keyword')||'',account:identity(),scope:'当前已加载列表；卡片尚未精读',
      search_controls:[...document.querySelectorAll('[id*="search-input"],input[placeholder*="搜索"],textarea[placeholder*="搜索"]')].map(e=>({tag:e.tagName,id:e.id,classes:e.className,editable:e.isContentEditable,placeholder:e.getAttribute('placeholder')})).slice(0,5)};
  }
  if(action==='scroll'){
    if(location.hostname==='creator.xiaohongshu.com'&&location.pathname==='/new/note-manager'){
      const cards=[...document.querySelectorAll('.note-card')];
      if(!cards.length)return {scrolled:false,reason:'当前没有笔记卡片'};
      let root=cards[0].parentElement;
      while(root&&!(root.scrollHeight>root.clientHeight+1&&/auto|scroll/.test(getComputedStyle(root).overflowY)))root=root.parentElement;
      if(!root)return {scrolled:false,reason:'当前笔记列表没有可滚动容器'};
      check();root.scrollBy({top:args.direction==='up'?-700:700,behavior:'instant'});
      // A minimized renderer may defer the native scroll event until a frame.
      check();root.dispatchEvent(new Event('scroll',{bubbles:false}));
      return {scrolled:true,loaded_before:cards.length,top:root.scrollTop,total:root.scrollHeight,height:root.clientHeight,message:'仅滚动到已加载列表边缘；另行读取后核对是否加载更多'};
    }
    const root=document.querySelector('.note-detail-mask .comments-container,.note-detail-mask .note-scroller')||(location.hostname==='creator.xiaohongshu.com'?document.querySelector('.publish-page'):null)||document.scrollingElement;
    check(); root.scrollBy({top:Math.min(innerHeight*0.75,700)*(args.direction==='up'?-1:1),behavior:'instant'});
    return {scrolled:true};
  }
  const expected=args.note_id;
  if(['open_note','read_note','close_note'].includes(action)&&! /^[a-f0-9]{24}$/.test(expected||''))throw Error('笔记 ID 无效');
  if(action==='open_note'){
    const link=[...document.querySelectorAll('section.note-item a[href],.note-item a[href]')].find(e=>noteId(e.href)===expected&&visible(e));
    if(!link)throw Error('目标卡片已失效，请重新读取列表');
    check(); link.click();
    return until(() => noteId(location.href)===expected&&visible(document.querySelector('.note-detail-mask,.note-container'))&&detailReady(expected)&&{note_id:expected,opened:true,detail_ready:true}, 20000, '详情数据未在时限内加载完整，未把列表摘要当正文');
  }
  if(action==='close_note'){
    if(noteId(location.href)!==expected)throw Error('当前详情已改变，未关闭其他页面');
    const close=[...document.querySelectorAll('.close-circle,.note-detail-mask .close,.note-detail-mask [aria-label="关闭"]')].find(visible);
    if(!close)throw Error('未找到详情关闭按钮，请手动返回列表');
    check(); close.click();
    return until(() => noteId(location.href)!==expected&&!visible(document.querySelector('.note-detail-mask'))&&{closed:true}, 4000, '详情关闭状态未能核对，请人工返回列表');
  }
  if(action==='read_note'){
    if(noteId(location.href)!==expected)throw Error('当前地址与目标笔记 ID 不一致');
    const root=[...document.querySelectorAll('.note-detail-mask,.note-container')].find(visible);
    if(!root)throw Error('未找到可见详情；未用列表卡片冒充正文');
    const state=window.__INITIAL_STATE__?.note?.noteDetailMap;
    const record=state?.[expected];const note=record?.note||record;
    if(note?.noteId&&note.noteId!==expected)throw Error('页面状态属于另一篇笔记');
    if(!detailReady(expected))throw Error('当前仍是列表摘要，详情数据尚未加载完整；未采集，请稍后重试');
    const bodyNode=root.querySelector('#detail-desc,.desc');
    const body=String(note?.desc||'').trim()||text(bodyNode)||bodyNode?.textContent?.trim()||'';
    const title=text(root.querySelector('#detail-title,.title'))||String(note?.title||'');
    const comments=[...new Set([...root.querySelectorAll('.comment-item .content,.comment-item .note-text')].filter(visible).map(text).filter(Boolean))].slice(0,40);
    const imageUrls=[];
    for(const img of note?.imageList||[]){const candidate=img.urlDefault||img.url||img.infoList?.find(i=>i.imageScene==='WB_DFT')?.url;if(candidate)imageUrls.push(candidate);}
    if(!imageUrls.length)for(const img of root.querySelectorAll('.swiper-slide img,.media-container img'))if(img.currentSrc||img.src)imageUrls.push(img.currentSrc||img.src);
    if(!body&&!comments.length&&!imageUrls.length)throw Error('未读到正文、评论或实际图片；可在浏览器展开详情后重试');
    return {note_id:expected,title:title||body.slice(0,60),text:body,comments,author:text(root.querySelector('.author-wrapper .username,.author-container .username'))||String(note?.user?.nickname||''),
      metrics:note?.interactInfo||{},image_urls:[...new Set(imageUrls)].slice(0,12),images_reported:new Set(imageUrls).size,observed_at:new Date().toISOString(),published_at:Number.isFinite(Number(note?.time))&&Number(note.time)>0?new Date(Number(note.time)).toISOString():'未注明',account:identity(),
      extraction:{detail_ready:true,body_element_found:!!bodyNode,state_desc_length:String(note?.desc||'').length,state_found:!!record,state_fields:Object.keys(record||{}).slice(0,20),note_fields:Object.keys(note||{}).slice(0,40)}};
  }
  throw Error('未开放此站内动作');
}

// Native text-to-image workflow: bounded stages, exact controls, no publish action.
async function xhsNativePreview(args, {visible,text,check,until,identity}) {
  if(location.hostname!=='creator.xiaohongshu.com')throw Error('请先在绑定页进入创作者中心');
  const trace=phase=>{const list=window.__xhsNativeTrace||=[];list.push({phase,at:Date.now(),screen:text(document.body).slice(0,350),buttons:[...document.querySelectorAll('button,[role=button],.d-button')].filter(visible).map(e=>({text:text(e),disabled:e.disabled})).slice(-12)});if(list.length>20)list.shift();};
  trace('start');
  const same=(a,b)=>String(a||'').replace(/\s/g,'')===String(b||'').replace(/\s/g,'');
  const wait=async(...a)=>{const value=await until(...a);if(value?.blocked){const error=Error('平台要求处理验证');error.platform_blocked=value.blocked;throw error;}return value;};
  const paragraphs=value=>{
    const escape=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    return value.split(/\n\s*\n/).map(part=>'<p>'+escape(part).replace(/\n/g,'<br>')+'</p>').join('');
  };
  if(Array.from(args.text||'').length>500)throw Error('独立配图文字须不超过500字符；请修改配图短文，完整正文可保留');
  const key=args.draft_id&&args.revision?args.draft_id+':'+args.revision:args.text;
  const getBox=()=>[...document.querySelectorAll('[role="textbox"][contenteditable="true"]')].filter(e=>visible(e)||e.closest('.text-editor-container'));
  const templateRoot=()=>{const root=document.querySelector('.image-overview');return visible(root)?root:null;};
  const images=()=>[...document.querySelectorAll('.image-overview .swiper-img')].map(i=>i.currentSrc||i.src).filter(Boolean);
  const caption=()=>document.querySelector('div.tiptap.ProseMirror,div.ProseMirror[contenteditable="true"],div.ql-editor');
  const title=()=>document.querySelector('input[placeholder*="填写标题"],input[placeholder*="标题"],div.d-input input');
  const button=(label,root=document)=>{
    if(!root)throw Error(label+'区域未就绪');
    const matches=[...root.querySelectorAll('button,[role="button"],.d-button,.edit-text-button')].filter(e=>visible(e)&&text(e)===label);
    if(matches.length!==1||matches[0].disabled||matches[0].getAttribute('aria-disabled')==='true'||matches[0].classList?.contains('disabled'))throw Error(label+'控件未唯一就绪，当前内容已保留');
    return matches[0];
  };
  // Browser navigation and account identity can settle before the upload UI mounts.
  await wait(()=>getBox().length||templateRoot()||title()||[...document.querySelectorAll('.creator-tab')].some(e=>visible(e)&&text(e)==='上传图文')||[...document.querySelectorAll('button')].some(e=>visible(e)&&text(e)==='文字配图'),15000,'创作者编辑器内容未就绪，未点击其他入口');
  let record=window.__xhsNativePreview;
  if(record&&record.key!==key){
    const empty=!templateRoot()&&!title()?.value&&!text(caption())&&!document.querySelectorAll('.img-preview-area .pr').length&&getBox().every(e=>!text(e));
    const ownedWriting=record.phase==='writing'&&record.key.startsWith(args.draft_id+':')&&getBox().every((box,i)=>!text(box)||same(text(box),xhsNativePages(record.text)[i]));
    if(empty){delete window.__xhsNativePreview;record=null;}
    else if(ownedWriting){record.key=key;record.previous_text=record.text;}
    else throw Error('页面中保留的是另一版本的原生配图，未覆盖');
  }
  // A recovered template can only be adopted after the caller reviewed its exact images.
  if(templateRoot()&&!record){
    const urls=images();
    if(!Array.isArray(args.resume_images)||JSON.stringify(urls)!==JSON.stringify(args.resume_images)||!urls.length)throw Error('当前已有未关联的原生图片，请先核对属于当前稿件；未生成或覆盖');
    record=window.__xhsNativePreview={key,text:args.text,phase:'templates',image_urls:urls,recovered:true};
  }
  if(!record&&!getBox().length&&!templateRoot()){
    if(text(caption())||title()?.value||document.querySelector('.img-preview-area img,.image-list img')||[...document.querySelectorAll('input[type="file"]')].some(e=>e.files?.length))throw Error('编辑器已有其他内容，未覆盖');
    let entry=[...document.querySelectorAll('button')].find(e=>visible(e)&&text(e)==='文字配图');
    if(!entry){const tab=[...document.querySelectorAll('.creator-tab')].find(e=>visible(e)&&text(e)==='上传图文');if(!tab)throw Error('未找到上传图文入口');check();tab.click();await wait(()=>[...document.querySelectorAll('button')].some(e=>visible(e)&&text(e)==='文字配图'),6000,'上传图文入口未就绪');}
    entry=button('文字配图');check();entry.click();trace('entry_clicked');
    await wait(()=>getBox().length===1,8000,'原生文字编辑器未就绪，未重复点击');
  }
  if(getBox().length&&!templateRoot()&&!title()&&text(document.body).includes('写文字')){
    let boxes=getBox();trace('writer_ready');
    const mountedAt=Date.now()+450;await wait(()=>getBox().every(e=>e.editor?.isInitialized)&&Date.now()>=mountedAt,5000,'原生文字编辑器尚未完成挂载');boxes=getBox();
    const current=boxes.map(text).join('\n\n'),pages=xhsNativePages(args.text);
    const priorPages=xhsNativePages(record?.previous_text||record?.text||args.text);
    const reviewedWriting=Array.isArray(args.resume_writing)&&JSON.stringify(args.resume_writing)===JSON.stringify(boxes.map(text));
    const savedWriting=record?.writing_snapshot&&JSON.stringify(record.writing_snapshot)===JSON.stringify(boxes.map(text));
    const resumable=record?.phase==='writing'&&(reviewedWriting||savedWriting||boxes.every((box,i)=>!text(box)||same(text(box),priorPages[i])));
    if(current&&!same(current,args.text)&&!resumable)throw Error('原生文字编辑器已有其他内容，未覆盖');
    if(boxes.length>pages.length&&!resumable)throw Error('原生编辑器已有额外卡片，未删除或覆盖');
    const slots=pages.concat(Array(Math.max(0,boxes.length-pages.length)).fill(''));
    if(record?.phase==='generating')throw Error('本轮已请求生图，尚未核对结果，未重复请求');
    record=window.__xhsNativePreview={key,text:args.text,phase:'writing',page_count:pages.length,format:'manual-breaks-v1'};
    const fill=async(box,value)=>{
      check();if(!box.editor?.commands?.setContent)throw Error('原生编辑器接口未就绪，未写入或生成');
      const content=[];value.split('\n').forEach((line,i)=>{if(i)content.push({type:'hardBreak',attrs:{'data-break-type':'manual'}});if(line)content.push({type:'text',text:line});});
      box.editor.commands.setContent({type:'doc',content:[{type:'paragraph',content}]},true);
      box.editor.emit('update',{editor:box.editor,transaction:box.editor.state.tr});
      // A shared 300ms debounce saves only the most recently edited card.
      const settledAt=Date.now()+450;
      await wait(()=>Date.now()>=settledAt,3000,'平台卡片保存未就绪，未继续写入');
      try{await wait(()=>same(text(box),value),4000,'当前卡片文字未能核对，未继续添加');}
      catch(error){record.writing_snapshot=getBox().map(text);throw error;}
    };
    // Clear only the verified task-owned writing buffer, backwards. Native
    // deletion merges a following automatic overflow card; clear its tail first.
    for(let index=boxes.length-1;index>=0;index--)await fill(boxes[index],'');
    for(let index=0;index<slots.length;index++){
      if(index>=boxes.length){
        const add=document.querySelector('.add-text-item-button');
        if(!add||!visible(add))throw Error('未找到再写一张入口，文字已保留');
        const count=boxes.length;check();add.click();
        await wait(()=>getBox().length===count+1,12000,'新卡片编辑器未就绪，未重复添加');boxes=getBox();
        await wait(()=>boxes[index].editor?.isInitialized,5000,'新卡片尚未完成挂载');
      }
      await fill(boxes[index],slots[index]);
    }
    trace('pages_filled');
    if(!same(boxes.map(text).join('\n\n'),args.text)||boxes.some((box,i)=>!same(text(box),slots[i])))throw Error('原生卡片文字未能完整核对，未生成');
    await wait(()=>!document.querySelector('.tip-text-length .length-error'),2000,'平台文字总量超过500字，未生成图片；请缩短独立配图短文，完整正文可保留');
    if(record?.phase==='generating')throw Error('本轮已请求生图，尚未核对结果，未重复请求');
    const generate=await wait(()=>{try{return button('生成图片');}catch(_){return false;}},8000,'生成图片控件未在时限内就绪，文字已保留');check();
    record=window.__xhsNativePreview={key,text:args.text,phase:'generating',page_count:pages.length,format:'manual-breaks-v1'};
    generate.click();
    const ready=await wait(()=>templateRoot()&&images().length,30000,'已请求生图，结果尚未就绪；未重复生成');
    if(ready?.blocked)return ready;
    record.phase='templates';record.image_urls=images();
    if(record.image_urls.length!==record.page_count)throw Error('原生生成图片数量与已核对的文字卡片不符');
  }
  if(templateRoot()){
    if(!record||record.key!==key)throw Error('原生图片与稿件关系未确认');
    if(args.template){
      const choices=[...document.querySelectorAll('.cover-item-container')].filter(e=>text(e.querySelector('.cover-name'))===args.template);
      if(choices.length!==1)throw Error('没有唯一匹配的原生模板，未更换当前样式');
      const choice=choices[0].querySelector('.cover-item');
      if(!choice.classList.contains('active')){check();choice.click();await wait(()=>choice.classList.contains('active')&&images().length&&images()[0]===(choice.querySelector('img')?.currentSrc||choice.querySelector('img')?.src),15000,'模板仍在加载，未重复点击');}
    }
    const ready=await wait(()=>{const imgs=[...document.querySelectorAll('.image-overview .swiper-img')];return imgs.length&&imgs.every(i=>i.complete&&i.naturalWidth>0);},15000,'原生图片未全部加载');
    if(ready?.blocked)return ready;
    record.image_urls=images();
    record.template=text(document.querySelector('.cover-item.active')?.closest('.cover-item-container')?.querySelector('.cover-name'));
    if(record.phase==='advancing')throw Error('已请求进入最终编辑器，未重复点击下一步');
    const next=button('下一步',document.querySelector('.overview-footer'));check();record.phase='advancing';next.click();
    const final=await wait(()=>title()&&caption()&&document.querySelectorAll('.img-preview-area .pr').length,30000,'进入编辑器仍在处理中，未重复生成或上传');
    if(final?.blocked)return final;
  }
  if(!record||!title()||!caption())throw Error('原生流程未到达可核对的最终编辑器');
  if(args.template&&record.template!==args.template)throw Error('当前已是最终预览，不能静默更换原生模板；请保留稿件后在新一轮生图时选择模板');
  const t=title(),body=caption(),count=document.querySelectorAll('.img-preview-area .pr').length;
  if(count!==record.image_urls.length)throw Error('最终图片数量与原生生成结果不符');
  if(t.value&&!same(t.value,args.title)&&!same(t.value,args.text.split('\n')[0]))throw Error('最终编辑器已有其他标题，未覆盖');
  const generatedDefault=record.phase==='advancing'&&same(text(body),xhsNativePages(record.text)[0]);
  if(text(body)&&!same(text(body),args.body)&&!same(text(body),args.text)&&!generatedDefault)throw Error('最终编辑器已有其他正文，未覆盖');
  check();if(t.value!==args.title){Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(t,args.title);t.dispatchEvent(new Event('input',{bubbles:true}));}
  if(!same(text(body),args.body)){
    if(!body.editor?.commands?.setContent)throw Error('最终正文编辑器接口未就绪，未覆盖');
    body.editor.commands.setContent(paragraphs(args.body),true);
    const settledAt=Date.now()+450;await wait(()=>Date.now()>=settledAt,3000,'最终正文仍在保存');
  }
  await wait(()=>same(t.value,args.title)&&same(text(body),args.body),5000,'标题或完整正文未能核对');
  await wait(()=>!(/上传中|正在上传/.test(text(document.body))),20000,'原生图片仍在处理中，未重新上传');
  record.phase='ready';
  return {ready:true,published:false,title:t.value,body:text(body),image_count:count,image_urls:record.image_urls,template:record.template,account:identity(),text_verified:true,message:'原生配图与最终标题、正文、图片数量已核对，尚未发布。'};
}

function xhsNativePages(value, maximum=140){
  const pages=[];let current='';
  const lines=text=>text.split('\n').reduce((total,line)=>total+Math.max(1,Math.ceil(Array.from(line).length/18)),0);
  for(const paragraph of value.split(/\n\s*\n/)){
    const pieces=[];let pending='';
    for(const character of Array.from(paragraph)){
      if(Array.from(pending+character).length>maximum||lines(pending+character)>8){if(pending.trim())pieces.push(pending);pending='';}
      pending+=character;
    }
    if(pending)pieces.push(pending);
    for(const piece of pieces){
      const candidate=current?current+'\n\n'+piece:piece;
      if(Array.from(candidate).length>maximum||lines(candidate)>8){if(current)pages.push(current);current=piece;}
      else current=candidate;
    }
  }
  if(current)pages.push(current);
  if(!pages.length||pages.length>12)throw Error('原生文字页数无效');
  return pages;
}
