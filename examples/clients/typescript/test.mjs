import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {Observation} from './dist/client.js';

const result=JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json',import.meta.url))).results[0];
const envelope={api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};
test('expiry, disconnect, suspension and unbounded transit remain UNKNOWN',()=>{
 const o=new Observation();o.accept(envelope,0);
 assert.equal(o.view(50).label,'delayed_observation');assert.equal(o.view(50).current_state,'UNKNOWN');
 assert.equal(o.view(101).label,'expired');o.accept(envelope,100);assert.equal(o.view(0).label,'expired');
 o.accept(envelope,0);o.disconnect();assert.equal(o.view(0).label,'expired');
});
test('unknown enum or extra field rejects and clears old scene',()=>{
 const o=new Observation();o.accept(envelope,0);
 assert.throws(()=>o.accept({...envelope,result:{...result,state:'SAFE'}},0));
 assert.equal(o.view(0).label,'expired');
 assert.throws(()=>o.accept({...envelope,person_identity:'forbidden'},0));
});

const invalidClocks = [NaN, Infinity, -Infinity, -1, '50', null, true];
for (const clock of invalidClocks) {
 test(`invalid receipt clock ${String(clock)} clears the observation`,()=>{
  const o=new Observation();o.accept(envelope,0);
  assert.throws(()=>o.accept(envelope,clock),{message:'invalid_clock'});
  assert.equal(o.view(50).label,'expired');
 });
 test(`invalid render clock ${String(clock)} irreversibly expires the observation`,()=>{
  const o=new Observation();o.accept(envelope,0);
  assert.equal(o.view(clock).label,'expired');
  assert.equal(o.view(50).label,'expired');
 });
}
test('clock rollback after a render cannot extend an observation',()=>{
 const o=new Observation();o.accept(envelope,0);
 assert.equal(o.view(80).label,'delayed_observation');
 assert.equal(o.view(70).label,'expired');
 assert.equal(o.view(90).label,'expired');
});
test('caller mutations cannot extend the validated lease or alter observations',()=>{
 const input=structuredClone(envelope);
 const o=new Observation();o.accept(input,0);
 const expected=structuredClone(o.view(0));
 input.clock.valid_for_ms=Infinity;
 input.result.state='SAFE';
 input.result.tracks[0].sources.length=0;
 input.result.tracks[0].covariance[0]=999;
 assert.deepEqual(o.view(50),expected);
 assert.equal(o.view(101).label,'expired');
});
test('mutating a returned covariance cannot alter later renders',()=>{
 const o=new Observation();o.accept(structuredClone(envelope),0);
 const expected=structuredClone(o.view(0));
 const first=o.view(0);first.uncertainty[0][0]=999;
 assert.deepEqual(o.view(50),expected);
});
test('fractional monotonic clocks preserve the frozen inclusive lease boundary',()=>{
 const o=new Observation();o.accept(envelope,0.5);
 assert.equal(o.view(100.5).label,'delayed_observation');
 assert.equal(o.view(100.501).label,'expired');
});

test('ordinary object serialization does not disclose the retained scene',()=>{
 const input=structuredClone(envelope);
 input.session='e'.repeat(32);input.result.tracks[0].id='ephemeral-test-only';
 const o=new Observation();o.accept(input,0);
 const reflected=JSON.stringify(Object.getOwnPropertyDescriptors(o));
 assert.ok(!reflected.includes(input.session),'reflection must not export the transport handle');
 assert.ok(!JSON.stringify(o).includes('ephemeral-test-only'),'serialization must not export a track identifier');
 assert.equal(o.view(50).label,'delayed_observation');
});
test('a JavaScript property collision cannot extend the accepted lease',()=>{
 const o=new Observation();o.accept(envelope,0);
 o.received=50;
 assert.equal(o.view(101).label,'expired');
});
test('a JavaScript property collision cannot replace an admitted scene',()=>{
 const o=new Observation();o.accept(envelope,0);
 const expected=o.view(0);
 o.scene={...envelope,result:{...result,state:'FORGED'}};
 assert.deepEqual(o.view(50),expected);
});
test('a failing input getter cannot leave a reentrant observation admitted',()=>{
 const o=new Observation();
 const input={get result(){o.accept(envelope,0);throw new Error('input details');}};
 assert.throws(()=>o.accept(input,0),{message:'invalid_event'});
 assert.equal(o.view(0).label,'expired');
});

test('observer deletes its session even when the final display callback throws',async t=>{
 const {observe}=await import('./dist/client.js');
 const requests=[];
 const controller=new AbortController();
 t.mock.method(globalThis,'fetch',async (url,options)=>{
  requests.push({url,options});
  if(options.method==='POST') return Response.json({session:'b'.repeat(32)});
  if(options.method==='DELETE') return new Response(null,{status:204});
  return new Response('');
 });
 await assert.rejects(observe('http://127.0.0.1:8765','test-token','bench',state=>{
  assert.equal(state.current_state,'UNKNOWN');
  assert.equal(state.label,'expired');
  controller.abort();
  throw new Error('display_failure');
 },controller.signal),{message:'display_failure'});
 assert.equal(requests.length,3,'session must be released after renderer failure');
 const cleanup=requests[2];
 assert.equal(cleanup.url,`http://127.0.0.1:8765/api/v1/sessions/${'b'.repeat(32)}`);
 assert.equal(cleanup.options.method,'DELETE');
 assert.equal(cleanup.options.headers.Authorization,'Bearer test-token');
 assert.notEqual(cleanup.options.signal,controller.signal);
 assert.equal(cleanup.options.signal.aborted,false);
});

for (const stall of ['headers','body','body-close']) {
 test(`watchdog renderer failure aborts stalled ${stall} and releases the session`,async t=>{
  const {observe}=await import('./dist/client.js');
  const caller=new AbortController();
  const failure=new Error('renderer_failure');
  const timer=Symbol('watchdog');
  let tick,streamSignal,ready;
  let displays=0;
  const requests=[],cleared=[];
  const opened=new Promise(resolve=>{ready=resolve;});
  t.mock.method(globalThis,'setInterval',callback=>{tick=callback;return timer;});
  t.mock.method(globalThis,'clearInterval',handle=>{cleared.push(handle);});
  t.mock.method(globalThis,'fetch',async (url,options)=>{
   requests.push({url,options});
   if(options.method==='POST') return Response.json({session:'c'.repeat(32)});
   if(options.method==='DELETE') return new Response(null,{status:204});
   streamSignal=options.signal;
   ready();
   if(stall==='headers') return new Promise((resolve,reject)=>{
    streamSignal.addEventListener('abort',()=>reject(streamSignal.reason),{once:true});
   });
   return new Response(new ReadableStream({start(controller){
    streamSignal.addEventListener('abort',()=>{
     if(stall==='body-close') controller.close();
     else controller.error(streamSignal.reason);
    },{once:true});
   }}));
  });
  const outcome=observe('http://127.0.0.1:8765','test-token','bench',state=>{
   displays++;
   assert.equal(state.current_state,'UNKNOWN');
   throw failure;
  },caller.signal).then(()=>null,error=>error);
  try {
   await opened;
   assert.doesNotThrow(()=>tick(),'watchdog exceptions must reach the observer promise');
   assert.equal(streamSignal.aborted,true);
   assert.doesNotThrow(()=>tick(),'a queued tick must not call the failed renderer again');
   assert.equal(caller.signal.aborted,false,'internal failure must not abort the caller');
   assert.equal(await outcome,failure);
   assert.equal(displays,1,'failed renderer must not be called again during teardown');
   assert.deepEqual(cleared,[timer]);
   assert.equal(requests.length,3);
   assert.equal(requests[2].options.method,'DELETE');
   assert.equal(requests[2].options.headers.Authorization,'Bearer test-token');
   assert.equal(requests[2].options.signal.aborted,false);
  } finally {
   caller.abort();
   await outcome;
  }
 });
}

const control=(sequence,kind='gap')=>({api_version:'1',kind,sequence,session:envelope.session,
 reason:kind==='gap'?'stream_gap':'source_lost',scene_state:'UNKNOWN',retryable:true});
async function consumeEvents(t,events) {
 const {observe}=await import('./dist/client.js');
 const requests=[],views=[];
 t.mock.method(performance,'now',()=>0);
 t.mock.method(globalThis,'setInterval',()=>0);
 t.mock.method(globalThis,'clearInterval',()=>{});
 t.mock.method(globalThis,'fetch',async (url,options)=>{
  requests.push({url,options});
  if(options.method==='POST') return Response.json({session:envelope.session});
  if(options.method==='DELETE') return new Response(null,{status:204});
  return new Response(events.map(event=>`data: ${JSON.stringify(event)}\n\n`).join(''));
 });
 const error=await observe('http://127.0.0.1:8765','test-token','bench',view=>views.push(view),
  new AbortController().signal).then(()=>null,error=>error);
 assert.equal(requests.length,3);
 assert.equal(requests[2].options.method,'DELETE');
 assert.equal(views.at(-1).label,'expired');
 assert.equal(views.at(-1).current_state,'UNKNOWN');
 return {error,views};
}
const invalidStreams=[
 ['foreign scene',[envelope,{...envelope,sequence:2,session:'d'.repeat(32)}]],
 ['duplicate scene',[envelope,envelope]],
 ['decreasing scene',[{...envelope,sequence:4},{...envelope,sequence:3}]],
 ['foreign health',[envelope,{...control(2,'health'),session:'d'.repeat(32)}]],
 ['duplicate gap',[envelope,control(1),{...envelope,sequence:2}]],
 ['scene older than health',[envelope,control(5,'health'),{...envelope,sequence:4}]],
 ['malformed health',[envelope,{...control(2,'health'),scene_state:'SAFE'}]],
 ['unsafe control sequence',[envelope,control(Number.MAX_SAFE_INTEGER+1)]],
 ['unknown event kind',[envelope,{...control(2),kind:'future'}]],
 ['null event',[envelope,null]],
];
for(const [name,events] of invalidStreams) {
 test(`stream rejects ${name} without refreshing the observation`,async t=>{
  const {error,views}=await consumeEvents(t,events);
  assert.equal(error?.message,'invalid_event');
  assert.equal(views.filter(view=>view.label==='delayed_observation').length,1);
  assert.ok(views.every(view=>view.current_state==='UNKNOWN'));
 });
}
test('stream accepts initial gap and increasing sequences across health clears',async t=>{
 const {error,views}=await consumeEvents(t,[control(0),envelope,control(2),
  {...envelope,sequence:4},control(7,'health'),{...envelope,sequence:8}]);
 assert.equal(error,null);
 assert.deepEqual(views.map(view=>view.label),['expired','delayed_observation','expired',
  'delayed_observation','expired','delayed_observation','expired']);
 assert.ok(views.every(view=>view.current_state==='UNKNOWN'));
});
