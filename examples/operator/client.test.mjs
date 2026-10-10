import assert from 'node:assert/strict';
import {test} from 'node:test';
import {parseHTML} from 'linkedom';
const module=await import('./dist/client.js').catch(error=>{if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;return {};});
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const delayed=()=>({label:'delayed_observation',current_state:'UNKNOWN',observed_state:'PRESENT',sources:['lwir'],uncertainty:[[0.1,0.1]]});
function setup(locale='en') {
 assert.equal(typeof module.mountObservationClient,'function');
 const {document,Event:DOMEvent}=parseHTML('<html><body><main></main><aside>unrelated</aside></body></html>');
 const window=new EventTarget(),timers=new Map();let visibility='visible',counter=0,resolve,signal,starts=0,reads=0,clearFails=false;
 window.setInterval=fn=>{timers.set(++counter,fn);return counter;};window.clearInterval=id=>timers.delete(id);
 Object.defineProperty(document,'defaultView',{value:window});Object.defineProperty(document,'visibilityState',{get:()=>visibility});
 // Deliberately non-clearing source: the containing view must still deny display
 // outside its own explicitly requested session, independent of adapter behavior.
 const session={view(){reads++;return delayed();},disconnect(){if(clearFails)throw new Error('private_clear');},start(value){starts++;signal=value;return new Promise(yes=>resolve=yes);}};
 const root=document.querySelector('main'),client=module.mountObservationClient(root,session,locale);
 return {root,client,session,document,window,DOMEvent,timers,reads:()=>reads,starts:()=>starts,signal:()=>signal,settle:()=>resolve(),failClear:()=>clearFails=true,
  tick(){for(const fn of [...timers.values()])fn();},
  click(feature){root.querySelector(`[data-feature="${feature}"]`).dispatchEvent(new DOMEvent('click'));},
  locale(value){root.querySelector(`button[lang="${value}"]`).dispatchEvent(new DOMEvent('click'));},
  observation:()=>root.querySelector('[data-help-topic^="observation."]').getAttribute('data-help-topic'),
  connection:()=>root.querySelector('[data-help-topic^="connection."]').getAttribute('data-help-topic'),
  hide(){visibility='hidden';document.dispatchEvent(new DOMEvent('visibilitychange'));}};
}
test('containing client denies reads until enabled AND explicitly started',async()=>{
 const s=setup();s.tick();assert.equal(s.reads(),0);assert.equal(s.observation(),'observation.expired');s.client.setEnabled(true);s.tick();assert.equal(s.reads(),0);
 s.click('connection.start');s.tick();assert.equal(s.observation(),'observation.delayed');s.click('connection.stop');assert.equal(s.observation(),'observation.expired');assert.equal(s.signal().aborted,true);
 s.settle();await turn();s.tick();assert.equal(s.observation(),'observation.expired');s.client.dispose();
});
test('one language selector synchronizes observation, connection and both help texts',async()=>{
 const s=setup();s.client.setEnabled(true);s.click('connection.start');s.tick();
 for(const language of ['sv-SE','en']) {s.locale(language);assert.deepEqual([...s.root.querySelectorAll('section')].map(n=>n.lang),[language,language]);assert.equal(s.observation(),'observation.delayed');assert.equal(s.connection(),'connection.requested');}
 assert.equal(s.root.querySelectorAll('button[lang]').length,2);s.client.setLocale('sv-SE');assert.match(s.root.textContent,/Stoppa/);assert.match(s.root.textContent,/Fördröjd/);s.settle();await turn();s.client.dispose();
});
test('permission withdrawal clears synchronously and reenabling does not revive old data',async()=>{
 const s=setup();s.client.setEnabled(true);s.click('connection.start');s.tick();s.client.setEnabled(false);
 assert.equal(s.observation(),'observation.expired');assert.equal(s.signal().aborted,true);s.client.setEnabled(true);s.tick();assert.equal(s.observation(),'observation.expired');s.click('connection.start');assert.equal(s.starts(),1);
 s.settle();await turn();s.tick();assert.equal(s.observation(),'observation.expired');s.client.dispose();
});
test('reentrant revocation inside a source read cannot publish its old return value',async()=>{
 const s=setup();s.client.setEnabled(true);s.click('connection.start');s.session.view=()=>{s.client.setEnabled(false);return delayed();};s.tick();assert.equal(s.observation(),'observation.expired');assert.ok(!s.root.textContent.includes('lwir'));s.settle();await turn();s.client.dispose();
});
test('failed withdrawal still removes sensor details and prevents a new session',async()=>{
 const s=setup();s.client.setEnabled(true);s.click('connection.start');s.tick();s.failClear();s.click('connection.stop');assert.equal(s.observation(),'observation.expired');assert.ok(!s.root.textContent.includes('lwir'));assert.ok(!s.root.textContent.includes('private'));s.settle();await turn();s.click('connection.start');assert.equal(s.starts(),1);s.client.dispose();
});
test('hidden page withdraws both display and session without restarting',async()=>{
 const s=setup();s.client.setEnabled(true);s.click('connection.start');s.tick();s.hide();assert.equal(s.observation(),'observation.expired');assert.equal(s.signal().aborted,true);s.settle();await turn();assert.equal(s.starts(),1);s.client.dispose();
});
test('dispose retires timers, detached controls and late completions',async()=>{
 const s=setup();s.client.setEnabled(true);s.click('connection.start');s.tick();const retained=s.root.firstElementChild,button=s.root.querySelector('[data-feature="connection.start"]');s.client.dispose();s.client.dispose();s.settle();await turn();button.dispatchEvent(new s.DOMEvent('click'));assert.equal(s.starts(),1);assert.equal(s.root.textContent,'');assert.ok(!retained.textContent.includes('lwir'));assert.equal(s.timers.size,0);assert.equal(s.document.querySelector('aside').textContent,'unrelated');
});
test('invalid host arguments leave the existing root untouched',()=>{
 assert.equal(typeof module.mountObservationClient,'function');const {document}=parseHTML('<main>existing</main>');const root=document.querySelector('main');
 assert.throws(()=>module.mountObservationClient(root,{},'en'),{message:'invalid_session_adapter'});assert.equal(root.textContent,'existing');
 assert.throws(()=>module.mountObservationClient(root,{view(){},disconnect(){},async start(){}},'sv'),{message:'unsupported_locale'});assert.equal(root.textContent,'existing');
});

test('invalid availability/locale cannot enable or partly translate the view',()=>{
 const s=setup();const before=s.root.textContent;assert.throws(()=>s.client.setEnabled('yes'),{message:'invalid_permission'});assert.throws(()=>s.client.setLocale('sv'),{message:'unsupported_locale'});assert.equal(s.root.textContent,before);s.click('connection.start');assert.equal(s.starts(),0);s.client.dispose();
});
test('client ADR rejects unknown claims at root and architecture boundaries',async()=>{
 const {readFileSync}=await import('node:fs');const {Ajv2020}=await import('../clients/typescript/node_modules/ajv/dist/2020.js');const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url)));
 const adr=read('./client-adr.json'),validate=new Ajv2020({strict:true}).compile(read('./client-adr.schema.json'));
 assert.equal(validate(adr),true,JSON.stringify(validate.errors));assert.equal(validate({...adr,production_qualified:true}),false);assert.equal(validate({...adr,c4:{...adr.c4,certified:true}}),false);
});

for (const event of ['pageshow','resume']) {
 test(`containing client rejects Start during ${event} source withdrawal`,async()=>{
  const s=setup();s.client.setEnabled(true);let attempt=true;
  s.session.disconnect=()=>{
   if(!attempt)return;attempt=false;
   s.client.setEnabled(true);s.click('connection.start');s.tick();
  };
  (event==='pageshow'?s.window:s.document).dispatchEvent(new (event==='pageshow'?Event:s.DOMEvent)(event));
  assert.equal(s.starts(),0,'adapter must not start inside the shared source clearer');
  assert.equal(s.reads(),0,'withdrawal must not admit a source read');
  await turn();assert.equal(s.observation(),'observation.expired');
  s.click('connection.start');assert.equal(s.starts(),1,'an independent later Start is allowed');
  s.tick();assert.equal(s.observation(),'observation.delayed');
  s.settle();await turn();s.client.dispose();
 });
}
