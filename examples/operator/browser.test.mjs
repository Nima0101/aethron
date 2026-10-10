import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync, existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {parseHTML} from 'linkedom';
import {Observation as NodeObservation} from '../clients/typescript/dist/client.js';

const directory = new URL('./browser-dist/', import.meta.url);
const read = name => readFileSync(new URL(name, directory));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const envelope = {api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),
  clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},
  result:JSON.parse(readFileSync(new URL('../../contracts/fixtures/v3/blackout-output.json',import.meta.url))).results[0]};
async function bundle() {
  assert.ok(existsSync(new URL('aethron-observation.mjs',directory)), 'standalone browser artifact must exist');
  // Relative imports cannot resolve from a data URL; no node_modules resolution base.
  return import(`data:text/javascript;base64,${read('aethron-observation.mjs').toString('base64')}`);
}

test('standalone ESM exports only the public observation and presentation boundary',async()=>{
  const module=await bundle();
  assert.deepEqual(Object.keys(module).sort(),['Observation','createObservationSource','mountConnectionControls','mountObservationHost','mountObservationPanel','observe','presentObservation']);
  const result=module.presentObservation(new module.Observation().view(0),'en');
  assert.equal(result.state,'expired');
});
test('bundled admission matches Node for valid, invalid, expired and backwards-clock traces',async()=>{
  const {Observation}=await bundle();
  for(const mutate of [value=>value,value=>({...value,sequence:1.5}),value=>({...value,extra:true}),
    value=>({...value,clock:{...value.clock,valid_for_ms:101}})]) {
    const pair=[new Observation(),new NodeObservation()];
    const outcomes=pair.map(item=>{
      let error=null;try{item.accept(mutate(structuredClone(envelope)),10);}catch(caught){error=caught.message;}
      return {error,views:[10,110,111,9].map(now=>item.view(now))};
    });
    assert.deepEqual(outcomes[0],outcomes[1]);
  }
});
test('bundled observation withdraws reentrant and caller-mutated data',async()=>{
  const {Observation}=await bundle();const observation=new Observation();
  const input=structuredClone(envelope);observation.accept(input,0);
  input.result.state='UNKNOWN';assert.equal(observation.view(0).observed_state,envelope.result.state);
  const nested={...envelope,get result(){observation.disconnect();return envelope.result;}};
  assert.throws(()=>observation.accept(nested,0),{message:'invalid_event'});
  assert.equal(observation.view(0).label,'expired');
});
for (const phase of ['signal-composition','scheduler']) test(`bundled ${phase} failure withdraws and attempts deletion`,async t=>{
  const {observe}=await bundle();const requests=[],views=[];
  const caller=new AbortController();
  t.mock.method(globalThis,'setInterval',()=>{throw new Error('private_scheduler_marker');});
  t.mock.method(globalThis,'clearInterval',()=>assert.fail('no timer was allocated'));
  if(phase==='signal-composition')t.mock.method(AbortSignal,'any',()=>{throw new Error('private_signal_marker');});
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    requests.push(options.method);
    if(options.method==='POST')return Response.json({source_profile:'bench',session:envelope.session});
    assert.equal(options.method,'DELETE');return new Response(null,{status:204});
  });
  await assert.rejects(observe('http://127.0.0.1:8765','synthetic-token','bench',view=>views.push(view),caller.signal),
    {message:'stream_unavailable'});
  assert.deepEqual(requests,['POST','DELETE']);assert.equal(views.length,1);
  assert.equal(views[0].label,'expired');assert.deepEqual(views[0].sources,[]);
});
test('bundled panel renders bilingual fixed text and clears detached content',async()=>{
  const {Observation,mountObservationPanel}=await bundle();
  const {document}=parseHTML('<main></main>');const root=document.querySelector('main');
  const observation=new Observation();const panel=mountObservationPanel(root,()=>observation.view(0),'en');
  observation.accept(envelope,0);panel.refresh();assert.equal(root.querySelector('[role=status]').getAttribute('data-state'),'delayed');
  panel.setLocale('sv-SE');assert.equal(root.firstElementChild.lang,'sv-SE');
  const detached=root.querySelector('[role=status]');panel.dispose();
  assert.equal(root.textContent,'');assert.equal(detached.textContent,'');
});
const json=JSON.stringify(envelope);
for(const [name,text,expected] of [
  ['valid integer tokens',json,null],
  ['decimal integer token',json.replace('"sequence":1','"sequence":1.0'),'invalid_event'],
  ['duplicate key',json.replace('"sequence":1','"sequence":0,"sequence":1'),'invalid_event'],
  ['private malformed input','{"private-marker": }','invalid_event'],
]) test(`bundled authenticated stream: ${name}`,async t=>{
  const {observe}=await bundle();const views=[],requests=[];
  t.mock.method(performance,'now',()=>0);
  t.mock.method(globalThis,'setInterval',()=>0);
  t.mock.method(globalThis,'clearInterval',()=>{});
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    requests.push({url,options});
    if(options.method==='POST')return Response.json({source_profile:'bench',session:envelope.session});
    if(options.method==='DELETE')return new Response(null,{status:204});
    return new Response(new TextEncoder().encode(`event: scene\ndata: ${text}\n\n`));
  });
  const error=await observe('http://127.0.0.1:8765','synthetic-token','bench',view=>views.push(view),new AbortController().signal)
    .then(()=>null,error=>error.message);
  assert.equal(error,expected);
  assert.equal(views.filter(view=>view.label==='delayed_observation').length,expected?0:1);
  assert.equal(views.at(-1).label,'expired');
  assert.ok(views.every(view=>view.current_state==='UNKNOWN'));
  assert.equal(requests.at(-1).options.method,'DELETE');
  assert.ok(requests.every(({url,options})=>options.redirect==='error'&&!url.includes('synthetic-token')));
});
test('manifest binds a closed runtime input set and distributed license bytes',async()=>{
  await bundle();const manifest=JSON.parse(read('manifest.json'));
  assert.equal(manifest.format,'aethron-browser-component-v1');
  assert.equal(manifest.external_imports.length,0);
  assert.equal(manifest.qualified_browser,false);
  for(const [name,digest] of Object.entries(manifest.artifacts)) assert.equal(hash(read(name)),digest,name);
  for(const [name,digest] of Object.entries(manifest.inputs)) {
    assert.ok(!name.startsWith('/')&&!name.includes('..'),name);
    assert.equal(hash(readFileSync(new URL(`../../${name}`,import.meta.url))),digest,name);
  }
  assert.deepEqual(read('LICENSE'),readFileSync(new URL('../../LICENSE',import.meta.url)));
  assert.deepEqual(read('AJV-LICENSE'),readFileSync(new URL('../clients/typescript/node_modules/ajv/LICENSE',import.meta.url)));
  assert.ok(Object.keys(manifest.inputs).some(name=>name.endsWith('validators.cjs')));
  assert.ok(!Object.keys(manifest.inputs).some(name=>name.includes('linkedom')));
});
test('failed rebuild withdraws old output; recovery reproduces every artifact byte',async()=>{
  await bundle();const names=['aethron-observation.mjs','LICENSE','AJV-LICENSE','ESBUILD-LICENSE','manifest.json'];
  const before=names.map(name=>hash(read(name)));
  // Missing compiler command is a real child-process failure, not a mocked builder.
  try {
    assert.throws(()=>execFileSync(process.execPath,['build-browser.mjs'],{
      cwd:new URL('.',import.meta.url),env:{...process.env,PATH:''},stdio:'pipe',timeout:10000,
    }));
    for(const name of names) assert.equal(existsSync(new URL(name,directory)),false,name);
  } finally {
  execFileSync(process.execPath,['build-browser.mjs'],{cwd:new URL('.',import.meta.url),stdio:'pipe',timeout:150000});
  }
  assert.deepEqual(names.map(name=>hash(read(name))),before);
});

test('bundled observer withdraws on abort and retires its timer after cleanup',async t=>{
  const {observe}=await bundle();const views=[],requests=[],caller=new AbortController();
  let tick,controller,admitted;
  const ready=new Promise(resolve=>{admitted=resolve;});
  t.mock.method(performance,'now',()=>0);
  t.mock.method(globalThis,'setInterval',callback=>{tick=callback;return 0;});
  t.mock.method(globalThis,'clearInterval',()=>{});
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    requests.push(options.method??'GET');
    if(options.method==='POST')return Response.json({source_profile:'bench',session:envelope.session});
    if(options.method==='DELETE')return new Response(null,{status:204});
    return new Response(new ReadableStream({start(value){
      controller=value;value.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(envelope)}\n\n`));
    }}));
  });
  const observed=observe('http://127.0.0.1:8765','synthetic-token','bench',view=>{
    views.push(view);if(view.label==='delayed_observation')admitted();
  },caller.signal).then(()=>undefined,error=>error);
  try {
    await ready;caller.abort(new Error('private_abort_marker'));tick();
    assert.equal(views.at(-1).label,'expired');assert.deepEqual(views.at(-1).sources,[]);
    assert.equal(views.filter(view=>view.label==='delayed_observation').length,1);
  } finally {controller.close();assert.equal((await observed)?.message,'stream_unavailable');}
  assert.deepEqual(requests,['POST','GET','DELETE']);
  const count=views.length;tick();assert.equal(views.length,count);
});

test('bundled live source rechecks cancellation after a host clock read',async t=>{
  const {createObservationSource}=await bundle(),source=createObservationSource();
  const caller=new AbortController();let controller,signal;
  t.mock.method(performance,'now',()=>0);
  t.mock.method(globalThis,'setInterval',()=>assert.fail('live source must not own a scheduler'));
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    if(options.method==='POST')return Response.json({source_profile:'bench',session:envelope.session});
    if(options.method==='DELETE')return new Response(null,{status:204});
    signal=options.signal;
    return new Response(new ReadableStream({start(value){controller=value;}}));
  });
  const done=source.start('http://127.0.0.1:8765','synthetic-token','bench',caller.signal).then(()=>undefined,error=>error);
  const turn=()=>new Promise(resolve=>setImmediate(resolve));
  try {
    await turn();controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(envelope)}\n\n`));await turn();
    assert.equal(source.view().label,'delayed_observation');
    t.mock.method(performance,'now',()=>{caller.abort();return 0;});
    assert.equal(source.view().label,'expired');assert.equal(signal.aborted,true);
  } finally {controller.close();await done;}
  assert.equal((await done)?.message,'stream_unavailable');assert.equal(caller.signal.aborted,true);
});

test('bundled callback suppresses cancellation from its view clock',async t=>{
  const {observe}=await bundle(),caller=new AbortController(),views=[];
  let armed=false,reads=0;
  const response=new Response(`data: ${JSON.stringify(envelope)}\n\n`);
  t.mock.method(performance,'now',()=>{
    if(armed&&++reads===2)caller.abort(new Error('private_clock_abort_marker'));
    return 0;
  });
  t.mock.method(globalThis,'setInterval',()=>0);
  t.mock.method(globalThis,'clearInterval',()=>{});
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    if(options.method==='POST')return Response.json({source_profile:'bench',session:envelope.session});
    if(options.method==='DELETE')return new Response(null,{status:204});
    armed=true;return response;
  });
  const error=await observe('http://127.0.0.1:8765','synthetic-token','bench',view=>views.push(view),caller.signal)
    .then(()=>undefined,error=>error);
  assert.equal(caller.signal.aborted,true);
  assert.equal(error?.message,'stream_unavailable');
  assert.ok(views.length>0);assert.ok(views.every(view=>view.label==='expired'));
});

test('bundled connection controls stay offline until explicit host-enabled start',async()=>{
 const {mountConnectionControls}=await bundle();const {document,Event:DOMEvent}=parseHTML('<html><body><main></main></body></html>');
 Object.defineProperty(document,'defaultView',{value:new EventTarget()});Object.defineProperty(document,'visibilityState',{value:'visible'});
 let calls=0,finish,signal;const controls=mountConnectionControls(document.querySelector('main'),{start(value){calls++;signal=value;return new Promise(resolve=>{finish=resolve;});},disconnect(){}},'sv-SE');
 const start=document.querySelector('[data-feature="connection.start"]'),stop=document.querySelector('[data-feature="connection.stop"]');
 start.dispatchEvent(new DOMEvent('click'));assert.equal(calls,0);controls.setEnabled(true);start.dispatchEvent(new DOMEvent('click'));assert.equal(calls,1);
 stop.dispatchEvent(new DOMEvent('click'));assert.equal(signal.aborted,true);assert.equal(document.querySelector('[role=status]').getAttribute('data-state'),'stopping');
 finish();await new Promise(resolve=>setImmediate(resolve));assert.equal(document.querySelector('[role=status]').getAttribute('data-state'),'stopped');controls.dispose();assert.equal(document.querySelector('main').textContent,'');
});
