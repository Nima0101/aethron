import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import * as sdk from './dist/client.js';

const session={session:'a'.repeat(32),source_profile:'bench'};
const envelope={api_version:'1',kind:'scene',sequence:1,session:session.session,
  clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},
  result:JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json',import.meta.url))).results[0]};
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const bytes=value=>new TextEncoder().encode(`data: ${JSON.stringify(value)}\n\n`);
function setup(t) {
  assert.equal(typeof sdk.createObservationSource,'function','a fresh revocable source must be exported');
  const source=sdk.createObservationSource(),caller=new AbortController(),requests=[];
  let now=0,controller,eventSignal;
  t.mock.method(performance,'now',()=>now);
  t.mock.method(globalThis,'setInterval',()=>assert.fail('source must use the display host scheduler'));
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    requests.push({url,options});
    if(options.method==='POST')return Response.json(session);
    if(options.method==='DELETE')return new Response(null,{status:204});
    eventSignal=options.signal;
    return new Response(new ReadableStream({start(value){controller=value;}}));
  });
  return {source,caller,requests,start:()=>source.start('http://127.0.0.1:8765','synthetic-token','bench',caller.signal)
    .then(()=>undefined,error=>error),send:value=>controller.enqueue(bytes(value)),end:()=>controller.close(),
    now:value=>{now=value;},signal:()=>eventSignal};
}

test('source exposes only fresh view, disconnect and explicit start',t=>{
  const s=setup(t);
  assert.deepEqual(Object.keys(s.source).sort(),['disconnect','start','view']);
  assert.equal(s.source.view().label,'expired');s.source.disconnect();
  assert.deepEqual(s.requests,[]);
});
test('source preserves expiry and copy isolation without a timer',async t=>{
  const s=setup(t),done=s.start();await turn();s.send(envelope);await turn();
  try {
    assert.equal(s.source.view().label,'delayed_observation');
    const copy=s.source.view();copy.sources.length=0;
    assert.ok(s.source.view().sources.length>0);
    s.now(100);assert.equal(s.source.view().label,'delayed_observation');
    s.now(101);assert.equal(s.source.view().label,'expired');
  } finally {s.end();assert.equal(await done,undefined);}
  assert.equal(s.source.view().label,'expired');
});
for(const mode of ['disconnect','external-abort']) test(`${mode} withdraws before pending transport settles`,async t=>{
  const s=setup(t),done=s.start();await turn();s.send(envelope);await turn();
  assert.equal(s.source.view().label,'delayed_observation');
  if(mode==='disconnect')s.source.disconnect();else s.caller.abort(new Error('private_abort_marker'));
  assert.equal(s.source.view().label,'expired');assert.equal(s.signal().aborted,true);
  s.send({...envelope,sequence:2});s.end();
  assert.equal((await done)?.message,'stream_unavailable');
  assert.equal(s.source.view().label,'expired');
  assert.equal(s.requests.at(-1).options.method,'DELETE');
  assert.equal(s.requests.at(-1).options.signal.aborted,false);
});
test('overlap is rejected until deletion settles; restart needs an explicit new start',async t=>{
  const s=setup(t);let release,deleting;
  const pending=new Promise(resolve=>{release=resolve;}),started=new Promise(resolve=>{deleting=resolve;});
  const fetch=globalThis.fetch;
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    if(options.method==='DELETE'){deleting();await pending;}
    return fetch(url,options);
  });
  const done=s.start();await turn();
  assert.equal((await s.start())?.message,'observer_busy');
  assert.equal(s.requests.filter(r=>r.options.method==='POST').length,1);
  s.source.disconnect();s.end();await started;
  assert.equal((await s.start())?.message,'observer_busy');
  release();assert.equal((await done)?.message,'stream_unavailable');
  const next=s.start();await turn();s.send(envelope);await turn();
  assert.equal(s.source.view().label,'delayed_observation');s.end();assert.equal(await next,undefined);
  assert.equal(s.requests.filter(r=>r.options.method==='POST').length,2);
});
test('malformed ingress withdraws through the shared admission path',async t=>{
  const s=setup(t),done=s.start();await turn();s.send(envelope);await turn();
  assert.equal(s.source.view().label,'delayed_observation');
  s.send({...envelope,sequence:1.5});s.end();
  assert.equal((await done)?.message,'invalid_event');assert.equal(s.source.view().label,'expired');
});
test('failed endpoint and signal setup release the single-start gate without network access',async t=>{
  const s=setup(t);
  await assert.rejects(s.source.start('http://example.invalid','synthetic-token','bench',s.caller.signal),{message:'invalid_endpoint'});
  const any=t.mock.method(AbortSignal,'any',()=>{throw new Error('private_setup_marker');});
  await assert.rejects(s.source.start('http://127.0.0.1','synthetic-token','bench',s.caller.signal),{message:'stream_unavailable'});
  assert.deepEqual(s.requests,[]);any.mock.restore();
  const done=s.start();await turn();s.end();assert.equal(await done,undefined);
});

test('disconnect during session creation cannot expose a late admitted response',async t=>{
  const s=setup(t);let release;
  const pending=new Promise(resolve=>{release=resolve;});
  const fetch=globalThis.fetch;
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    if(options.method==='POST')await pending;
    return fetch(url,options);
  });
  const done=s.start();s.source.disconnect();
  assert.equal((await s.start())?.message,'observer_busy');
  release();await turn();s.send(envelope);s.end();
  assert.equal((await done)?.message,'stream_unavailable');
  assert.equal(s.source.view().label,'expired');assert.equal(s.requests.at(-1).options.method,'DELETE');
});

test('source decision conforms to a closed schema and four C4 views',async()=>{
  const {Ajv2020}=await import('ajv/dist/2020.js');
  const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
  const validate=new Ajv2020({strict:true}).compile(read('./source-adr.schema.json'));
  const adr=read('./source-adr.json');assert.equal(validate(adr),true,JSON.stringify(validate.errors));
  assert.equal(validate({...adr,qualified:true}),false);
  assert.equal(validate({...adr,c4:{...adr.c4,unreviewed:'claim'}}),false);
});

test('abort during the host clock read cannot return a revoked projection',async t=>{
  const s=setup(t),done=s.start();await turn();s.send(envelope);await turn();
  t.mock.method(performance,'now',()=>{s.caller.abort();return 0;});
  try {assert.equal(s.source.view().label,'expired');}
  finally {s.end();await done;}
});
