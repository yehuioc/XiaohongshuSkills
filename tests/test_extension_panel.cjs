const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function fixture(){
 const nodes=new Map(), calls=[];
 const element=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',value:'',checked:false,disabled:false,replaceChildren(){},append(){}});return nodes.get(id);};
 let listener,disconnect;
 const value={paired:true,binding:{tab_id:123,title:'指定研究页',url:'https://www.xiaohongshu.com/explore',control:true},busy:false,connected:true,message:'后台运行',version:'0.2.0'};
 const context=vm.createContext({document:{getElementById:element,createElement:()=>({})},chrome:{runtime:{
  sendMessage:async request=>{calls.push(request);return {result:value};},
  connect:()=>({onMessage:{addListener:fn=>listener=fn},onDisconnect:{addListener:fn=>disconnect=fn}})
 }}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/panel.js'),'utf8'),context);
 return {nodes,calls,update:change=>listener({...value,...change}),disconnect,async ready(){await new Promise(r=>setImmediate(r));}};
}
test('reopening a panel displays existing background control without changing it',async()=>{
 const f=fixture();await f.ready();assert.equal(f.nodes.get('control').checked,true);assert.match(f.nodes.get('binding').textContent,/关闭侧栏仍继续/);
 assert.deepEqual(f.calls.map(c=>c.action),['state']);f.disconnect();assert.equal(f.calls.length,1);
});
test('stop and locating actions go to the background owner, not local page scripts',async()=>{
 const f=fixture();await f.ready();await f.nodes.get('stop').onclick();await f.nodes.get('focus').onclick();
 assert.deepEqual(f.calls.map(c=>c.action),['state','stop','focus']);
 f.update({busy:true});assert.equal(f.nodes.get('bind').disabled,true);assert.equal(f.nodes.get('stop').disabled,false);
});
