import assert from 'node:assert/strict';
import {test} from 'node:test';
import {parseHTML} from 'linkedom';
import {mountObservationClient} from './dist/client.js';
import {readFileSync} from 'node:fs';
import * as inventory from './help-inventory.mjs';
const actions=['connection.start','connection.stop','locale.en','locale.sv-SE'];
function host() {
 const {document,Event:DOMEvent}=parseHTML('<html><body><main></main><aside></aside></body></html>');
 const window=new EventTarget();window.setInterval=()=>1;window.clearInterval=()=>{};
 Object.defineProperty(document,'defaultView',{value:window});Object.defineProperty(document,'visibilityState',{value:'visible'});
 let starts=0,signal,finish;const session={view:()=>null,disconnect(){},start(value){starts++;signal=value;return new Promise(resolve=>finish=resolve);}};
 return {document,DOMEvent,session,get starts(){return starts;},get signal(){return signal;},finish:()=>finish?.()};
}
function descriptions(root) {
 const buttons=[...root.querySelectorAll('button')];assert.deepEqual(buttons.map(b=>b.getAttribute('data-feature')).sort(),actions);
 return buttons.map(button=>{
  const id=button.getAttribute('aria-describedby');assert.ok(id);const p=root.ownerDocument.getElementById(id);assert.ok(p);assert.ok(root.contains(p));
  assert.equal(p.getAttribute('data-help-action'),button.getAttribute('data-feature'));assert.ok(p.textContent.trim());assert.equal(p.hidden,false);
  return p;
 });
}
test('all four actions have visible contextual descriptions without starting a session',()=>{
 const h=host(),root=h.document.querySelector('main'),client=mountObservationClient(root,h.session);
 try {assert.equal(descriptions(root).length,4);assert.equal(h.starts,0);assert.match(root.querySelector('[data-help-action="connection.stop"]').textContent,/local observation/);}
 finally {client.dispose();}
});
test('locale actions update every action description and preserve explicit start/stop',async()=>{
 const h=host(),root=h.document.querySelector('main'),client=mountObservationClient(root,h.session);
 const click=id=>root.querySelector(`[data-feature="${id}"]`).dispatchEvent(new h.DOMEvent('click'));
 try {
  descriptions(root);click('locale.sv-SE');for(const p of descriptions(root))assert.equal(p.lang,'sv-SE');
  assert.match(root.querySelector('[data-help-action="connection.start"]').textContent,/Begär/);assert.equal(h.starts,0);
  client.setEnabled(true);click('connection.start');assert.equal(h.starts,1);click('connection.stop');assert.equal(h.signal.aborted,true);h.finish();await new Promise(r=>setImmediate(r));
  click('locale.en');for(const p of descriptions(root))assert.equal(p.lang,'en');
 }finally{client.dispose();h.finish();}
});
test('descriptions are unique across simultaneous clients and withdrawn on dispose',()=>{
 const h=host(),a=h.document.querySelector('main'),b=h.document.querySelector('aside');
 const first=mountObservationClient(a,h.session),second=mountObservationClient(b,h.session);
 const nodes=[...descriptions(a),...descriptions(b)];assert.equal(new Set(nodes.map(p=>p.id)).size,8);
 first.dispose();for(const p of nodes.slice(0,4))assert.equal(p.textContent,'');assert.equal(descriptions(b).length,4);second.dispose();
});
const source=()=>readFileSync(new URL('./src/action-help.ts',import.meta.url),'utf8');
function build(text=source()) {assert.equal(typeof inventory.createActionHelpInventory,'function');return inventory.createActionHelpInventory(text,new Uint8Array([1]),{head:'a'.repeat(40),modified:true});}
test('action inventory has exact bilingual coverage and unsigned byte bindings',()=>{
 const result=build();assert.deepEqual(result.topics.map(t=>t.id),actions);assert.equal(result.product_help_complete,false);assert.equal(result.release_sha,null);
 assert.match(result.source_sha256['action-help'],/^[0-9a-f]{64}$/);for(const topic of result.topics)assert.deepEqual(Object.keys(topic.translations),['en','sv-SE']);
});
for(const [name,mutate] of [
 ['new undocumented action',s=>s.replace("'connection.start' |", "'unshipped' | 'connection.start' |")],
 ['missing Swedish action',s=>s.replace("'locale.en': ['English', 'Visa", "'wrong': ['English', 'Visa")],
 ['executable text',s=>s.replace("['Start', 'Request", "[privateFunction(), 'Request")],
])test(`action inventory rejects ${name}`,()=>{assert.throws(()=>build(mutate(source())),{message:'unsupported_help_source'});});

test('action-help decision has a closed schema and no qualification extensions',async()=>{
 const {Ajv2020}=await import('../clients/typescript/node_modules/ajv/dist/2020.js');const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url)));
 const value=read('./action-help-adr.json'),validate=new Ajv2020({strict:true}).compile(read('./action-help-adr.schema.json'));
 assert.equal(validate(value),true,JSON.stringify(validate.errors));assert.equal(validate({...value,product_complete:true}),false);
 assert.equal(validate({...value,c4:{...value.c4,certified:true}}),false);
});

test('unchanged refresh preserves description text nodes',async()=>{
 const {mountObservationPanel}=await import('./dist/panel.js');const h=host(),root=h.document.querySelector('main');
 const panel=mountObservationPanel(root,()=>null);
 try {const paragraphs=[...root.querySelectorAll('[data-help-action]')],nodes=paragraphs.map(p=>p.firstChild);
  panel.refresh();paragraphs.forEach((p,index)=>assert.equal(p.firstChild === nodes[index],true));
 }finally{panel.dispose();}
});
