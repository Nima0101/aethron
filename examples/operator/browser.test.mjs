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
  assert.deepEqual(Object.keys(module).sort(),['Observation','mountObservationHost','mountObservationPanel','observe','presentObservation']);
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
