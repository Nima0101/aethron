import assert from 'node:assert/strict';
import {test} from 'node:test';
import {parseHTML} from 'linkedom';
const module=await import('./dist/connection.js').catch(error=>{if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;return {};});
const turn=()=>new Promise(resolve=>setImmediate(resolve));
function setup(locale='en') {
  assert.equal(typeof module.mountConnectionControls,'function');
  const {document,Event:DOMEvent}=parseHTML('<html><body><main>previous</main><aside>other</aside></body></html>');
  const window=new EventTarget();let visibility='visible',resolve,reject,calls=0,clears=0,signal;
  Object.defineProperty(document,'defaultView',{value:window});Object.defineProperty(document,'visibilityState',{get:()=>visibility});
  const operation={start(value){calls++;signal=value;return new Promise((yes,no)=>{resolve=yes;reject=no;});},disconnect(){clears++;}};
  const root=document.querySelector('main');
  const controls=module.mountConnectionControls(root,operation,locale);
  return {document,window,root,controls,operation,DOMEvent,calls:()=>calls,clears:()=>clears,signal:()=>signal,
    state:()=>root.querySelector('[role=status]').getAttribute('data-state'),
    click:id=>root.querySelector(`[data-feature="connection.${id}"]`).dispatchEvent(new DOMEvent('click')),
    resolve:()=>resolve(),reject:()=>reject(new Error('private_endpoint_token')),
    visibility(value){visibility=value;document.dispatchEvent(new DOMEvent('visibilitychange'));},
    emit(name){const doc=name==='freeze'||name==='resume';(doc?document:window).dispatchEvent(doc?new DOMEvent(name):new Event(name));}};
}
test('controls start unavailable and withdraw old state without network or auto start',()=>{
 const s=setup();assert.equal(s.state(),'unavailable');assert.equal(s.clears(),1);s.click('start');assert.equal(s.calls(),0);
 assert.equal(s.root.querySelector('button').getAttribute('type'),'button');s.controls.dispose();
});
test('explicit start is single-flight and stop keeps gate closed until settlement',async()=>{
 const s=setup();s.controls.setEnabled(true);assert.equal(s.state(),'idle');s.click('start');s.click('start');assert.equal(s.calls(),1);assert.equal(s.state(),'requested');
 s.click('stop');assert.equal(s.signal().aborted,true);assert.equal(s.state(),'stopping');s.click('start');assert.equal(s.calls(),1);
 s.resolve();await turn();assert.equal(s.state(),'stopped');s.click('start');assert.equal(s.calls(),2);s.resolve();await turn();s.controls.dispose();
});
test('failure guidance never renders arbitrary host errors and explicit retry is available',async()=>{
 const s=setup();s.controls.setEnabled(true);s.click('start');s.reject();await turn();assert.equal(s.state(),'failed');assert.ok(!s.root.textContent.includes('private'));s.click('start');assert.equal(s.calls(),2);s.resolve();await turn();s.controls.dispose();
});
for(const [leave,enter] of [['pagehide','pageshow'],['freeze','resume']])test(`${leave} cancels; ${enter} never reconnects`,async()=>{
 const s=setup();s.controls.setEnabled(true);s.click('start');s.emit(leave);assert.equal(s.signal().aborted,true);s.resolve();await turn();assert.equal(s.state(),'paused');s.click('start');assert.equal(s.calls(),1);
 s.emit(enter);assert.equal(s.state(),'stopped');assert.equal(s.calls(),1);s.controls.dispose();
});
test('visibility and host permission withdrawal cancel without automatic restart',async()=>{
 const s=setup();s.controls.setEnabled(true);s.click('start');s.visibility('hidden');assert.equal(s.signal().aborted,true);s.resolve();await turn();assert.equal(s.state(),'paused');s.visibility('visible');assert.equal(s.calls(),1);
 s.click('start');s.controls.setEnabled(false);assert.equal(s.signal().aborted,true);s.resolve();await turn();assert.equal(s.state(),'unavailable');s.controls.setEnabled(true);assert.equal(s.calls(),2);s.controls.dispose();
});
test('locale switches update all controls, guidance and contextual state together',async()=>{
 const s=setup();s.controls.setEnabled(true);s.click('start');s.controls.setLocale('sv-SE');assert.equal(s.root.querySelector('section').lang,'sv-SE');assert.match(s.root.textContent,/Starta/);assert.match(s.root.textContent,/Stoppa/);assert.equal(s.root.querySelector('details').getAttribute('data-help-topic'),'connection.requested');
 s.click('stop');s.reject();await turn();assert.equal(s.state(),'stopped');assert.ok(!s.root.textContent.includes('private'));s.controls.dispose();
});
test('dispose withdraws immediately and suppresses late completions and retained clicks',async()=>{
 const s=setup();s.controls.setEnabled(true);s.click('start');const button=s.root.querySelector('button'),status=s.root.querySelector('[role=status]');s.controls.dispose();const clears=s.clears();
 assert.equal(s.signal().aborted,true);assert.equal(s.root.textContent,'');assert.equal(status.textContent,'');button.dispatchEvent(new s.DOMEvent('click'));s.resolve();await turn();s.emit('pageshow');assert.equal(s.calls(),1);assert.equal(s.clears(),clears);assert.equal(s.document.querySelector('aside').textContent,'other');
});
test('disconnect failure latches failed and cannot be bypassed by enabling',()=>{
 const s=setup();s.operation.disconnect=()=>{throw new Error('private_failure');};s.controls.setEnabled(false);s.controls.setEnabled(true);s.click('start');assert.equal(s.calls(),0);assert.equal(s.state(),'failed');assert.ok(!s.root.textContent.includes('private'));s.controls.dispose();
});
test('invalid locale or permission input cannot modify the current state',()=>{
 const s=setup();assert.throws(()=>s.controls.setEnabled('yes'),{message:'invalid_permission'});assert.throws(()=>s.controls.setLocale('sv'),{message:'unsupported_locale'});assert.equal(s.state(),'unavailable');s.controls.dispose();
});

for(const locale of ['en','sv-SE'])test(`${locale}: every reachable state has local contextual guidance`,async()=>{
 const s=setup(locale),seen=new Set();
 function check(){const state=s.state();seen.add(state);const details=s.root.querySelector('details');assert.equal(details.getAttribute('data-help-topic'),`connection.${state}`);assert.ok(details.querySelector('p').textContent.length>30);assert.equal(s.root.querySelector('section').lang,locale);}
 check();s.controls.setEnabled(true);check();s.visibility('hidden');check();s.visibility('visible');s.click('start');check();s.click('stop');check();s.resolve();await turn();check();s.click('start');s.reject();await turn();check();
 assert.deepEqual([...seen].sort(),['failed','idle','paused','requested','stopped','stopping','unavailable']);s.controls.dispose();
});
test('synchronous host start failure uses fixed guidance and releases the gate',async()=>{
 const s=setup();s.operation.start=()=>{throw new Error('private_start');};s.controls.setEnabled(true);s.click('start');await turn();assert.equal(s.state(),'failed');assert.ok(!s.root.textContent.includes('private'));s.controls.dispose();
});
test('reentrant disconnect cannot recursively clear or enable a new request',()=>{
 const s=setup();let calls=0;s.operation.disconnect=()=>{calls++;s.controls.setEnabled(false);s.controls.setEnabled(true);s.click('start');};s.controls.setEnabled(false);assert.equal(calls,1);assert.equal(s.calls(),0);assert.equal(s.state(),'failed');s.controls.dispose();
});
test('actual SDK source and display withdraw immediately when Stop is activated',async t=>{
 const {createObservationSource}=await import('../clients/typescript/dist/client.js');
 const {mountObservationHost}=await import('./dist/lifecycle.js');
 const {readFileSync}=await import('node:fs');
 const source=createObservationSource(),s=setup();
 s.window.setInterval=()=>1;s.window.clearInterval=()=>{};
 const observationRoot=s.document.createElement('div');s.document.body.append(observationRoot);
 const host=mountObservationHost(observationRoot,source);
 let controller;const requests=[];
 t.mock.method(performance,'now',()=>0);
 t.mock.method(globalThis,'fetch',async(url,options)=>{
   requests.push(options.method??'GET');
   if(options.method==='POST')return Response.json({session:'a'.repeat(32),source_profile:'bench'});
   if(options.method==='DELETE')return new Response(null,{status:204});
   return new Response(new ReadableStream({start(value){controller=value;}}));
 });
 const result=JSON.parse(readFileSync(new URL('../../contracts/fixtures/v3/blackout-output.json',import.meta.url))).results[0];
 const scene={api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};
 s.operation.start=signal=>source.start('http://127.0.0.1:8765','synthetic-token','bench',signal);
 s.operation.disconnect=()=>{source.disconnect();host.refresh();};
 try{
  s.controls.setEnabled(true);s.click('start');await turn();controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(scene)}\n\n`));await turn();host.refresh();
  assert.equal(observationRoot.querySelector('[role=status]').getAttribute('data-state'),'delayed');
  s.click('stop');assert.equal(source.view().label,'expired');assert.equal(observationRoot.querySelector('[role=status]').getAttribute('data-state'),'expired');
  controller.close();await turn();assert.equal(s.state(),'stopped');assert.deepEqual(requests,['POST','GET','DELETE']);
 }finally{s.controls.dispose();host.dispose();}
});

test('connection decision has a closed schema and four architecture views',async()=>{
 const {readFileSync}=await import('node:fs');const {Ajv2020}=await import('../clients/typescript/node_modules/ajv/dist/2020.js');
 const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url)));
 const validate=new Ajv2020({strict:true}).compile(read('./connection-adr.schema.json'));const adr=read('./connection-adr.json');
 assert.equal(validate(adr),true,JSON.stringify(validate.errors));assert.equal(validate({...adr,qualified:true}),false);assert.equal(validate({...adr,c4:{context:'only'}}),false);
});
