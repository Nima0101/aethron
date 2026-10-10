import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {observe} from './dist/client.js';

const encode = text => new TextEncoder().encode(text);
const result = JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url))).results[0];
const scene = {api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),
  clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};
const wire = (value, eol='\n') => `event: ${value.kind}${eol}data: ${JSON.stringify(value)}${eol}${eol}`;
async function consume(t,chunks) {
  const requests=[],views=[];let cancelled=false;
  t.mock.method(performance,'now',()=>0);
  t.mock.method(globalThis,'setInterval',()=>0);
  t.mock.method(globalThis,'clearInterval',()=>{});
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    requests.push({url,options});
    if(options.method==='POST')return Response.json({source_profile:'bench',session:scene.session});
    if(options.method==='DELETE')return new Response(null,{status:204});
    let index=0;
    return new Response(new ReadableStream({
      pull(controller){if(index<chunks.length)controller.enqueue(chunks[index++]);else controller.close();},
      cancel(){cancelled=true;},
    }));
  });
  const error=await observe('http://127.0.0.1:8765','synthetic-token','bench',view=>views.push(view),
    new AbortController().signal).then(()=>null,error=>error);
  assert.equal(requests.at(-1).options.method,'DELETE');
  assert.equal(views.at(-1).label,'expired');
  assert.ok(views.every(view=>view.current_state==='UNKNOWN'));
  return {error,views,cancelled};
}

test('multiple bounded events in one large fetch chunk remain admissible',async t=>{
  const text=Array.from({length:100},(_,i)=>wire({...scene,sequence:i})).join('');
  assert.ok(encode(text).length>65536);
  const {error,views}=await consume(t,[encode(text)]);
  assert.equal(error,null);assert.equal(views.filter(v=>v.label==='delayed_observation').length,100);
});
test('CRLF and split UTF-8 preserve one named event',async t=>{
  const value=structuredClone(scene);value.result.tracks[0].id='synthetic-é';
  const chunks=Array.from(encode(wire(value,'\r\n')),byte=>Uint8Array.of(byte));
  const {error,views}=await consume(t,chunks);
  assert.equal(error,null);assert.equal(views.filter(v=>v.label==='delayed_observation').length,1);
});
test('all SSE data lines contribute to the single JSON object',async t=>{
  const text=`event: scene\ndata: {\ndata: ${JSON.stringify(scene).slice(1)}\n\n`;
  const {error,views}=await consume(t,[encode(text)]);
  assert.equal(error,null);assert.equal(views.filter(v=>v.label==='delayed_observation').length,1);
});
test('a UTF-8 event over 64 KiB is rejected before schema admission',async t=>{
  const value=structuredClone(scene);value.result.reasons=['é'.repeat(33000)];
  const text=wire(value);assert.ok(text.length<65536);assert.ok(encode(text).length>65536);
  const {error,views}=await consume(t,[encode(text)]);
  assert.equal(error?.message,'event_limit');assert.equal(views.filter(v=>v.label==='delayed_observation').length,0);
});
const json=JSON.stringify(scene);
for(const [name,text] of [
  ['duplicate root key',`data: ${json.replace('"sequence":1','"sequence":0,"sequence":1')}\n\n`],
  ['escaped duplicate key',`data: ${json.replace('"sequence":1','"sequence":0,"\\u0073equence":1')}\n\n`],
  ['duplicate nested key',`data: ${json.replace('"valid_for_ms":100','"valid_for_ms":0,"valid_for_ms":100')}\n\n`],
  ['mismatched named event',wire(scene).replace('event: scene','event: health')],
  ['ignored second object',`data: ${json}\ndata: {}\n\n`],
  ['truncated event',`data: ${json}\n`],
  ['malformed JSON with private marker','data: {"private-marker": }\n\n'],
]) {
  test(`stream rejects ${name} with a fixed error`,async t=>{
    const {error,views}=await consume(t,[encode(text)]);
    assert.equal(error?.message,'invalid_event');
    assert.equal(views.filter(v=>v.label==='delayed_observation').length,0);
  });
}
test('truncated UTF-8 at EOF cannot be silently discarded',async t=>{
  const {error}=await consume(t,[encode(wire(scene)),Uint8Array.of(0xc3)]);
  assert.equal(error?.message,'invalid_event');
});
for(const extra of [0,1]) {
  test(`raw event byte boundary with ${extra} excess bytes`,async t=>{
    const base=wire(scene);
    const text=':'+ 'x'.repeat(65536-encode(base).length-2+extra)+'\n'+base;
    assert.equal(encode(text).length,65536+extra);
    const {error,views}=await consume(t,[encode(text)]);
    assert.equal(error?.message,extra?'event_limit':undefined);
    assert.equal(views.filter(v=>v.label==='delayed_observation').length,extra?0:1);
  });
}
test('producer payload-only boundary remains an explicit rejected interoperability case',async t=>{
  const value=structuredClone(scene);value.result.reasons=[''];
  value.result.reasons[0]='x'.repeat(65536-encode(JSON.stringify(value)).length);
  assert.equal(encode(JSON.stringify(value)).length,65536);
  assert.ok(encode(wire(value)).length>65536);
  const {error}=await consume(t,[encode(wire(value))]);
  assert.equal(error?.message,'event_limit');
});
test('ingress failure clears state before pending reader cancellation',async t=>{
  let tick,release,started;
  const cancelling=new Promise(resolve=>{started=resolve;});
  const cleanup=new Promise(resolve=>{release=resolve;});
  const views=[];
  t.mock.method(performance,'now',()=>0);
  t.mock.method(globalThis,'setInterval',callback=>{tick=callback;return 0;});
  t.mock.method(globalThis,'clearInterval',()=>{});
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    if(options.method==='POST')return Response.json({source_profile:'bench',session:scene.session});
    if(options.method==='DELETE')return new Response(null,{status:204});
    return new Response(new ReadableStream({
      start(controller){controller.enqueue(encode(wire(scene)+'data: {broken}\n\n'));},
      cancel(){started();return cleanup;},
    }));
  });
  const observed=observe('http://127.0.0.1:8765','synthetic-token','bench',view=>views.push(view),
    new AbortController().signal).then(()=>null,error=>error);
  try {
    await cancelling;tick();
    assert.equal(views.at(-1).label,'expired');
  } finally {release();assert.equal((await observed)?.message,'invalid_event');}
});

for (const failureKind of ['parser', 'renderer']) {
  for (const cancellation of ['pending', 'rejecting']) {
    test(`${failureKind} failure survives ${cancellation} cancellation and attempts deletion`, async t => {
      let release, started, streamSignal, stream, settled = false;
      const cancelling = new Promise(resolve => { started = resolve; });
      const cleanup = new Promise(resolve => { release = resolve; });
      const requests = [], views = [];
      const rendererFailure = new Error('synthetic_renderer_failure');
      const caller = new AbortController();
      t.mock.method(performance, 'now', () => 0);
      t.mock.method(globalThis, 'setInterval', () => 0);
      t.mock.method(globalThis, 'clearInterval', () => {});
      t.mock.method(globalThis, 'fetch', async (url, options) => {
        requests.push({url, options});
        if (options.method === 'POST') return Response.json({source_profile:'bench',session: scene.session});
        if (options.method === 'DELETE') return new Response(null, {status: 204});
        streamSignal = options.signal;
        stream = new ReadableStream({
          start(controller) {
            controller.enqueue(encode(wire(scene) + (failureKind === 'parser' ? 'data: {broken}\n\n' : '')));
          },
          cancel() {
            started();
            return cancellation === 'pending' ? cleanup : Promise.reject(new Error('private_cancel_marker'));
          },
        });
        return new Response(stream);
      });
      const observed = observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => {
        views.push(view);
        if (failureKind === 'renderer' && view.label === 'delayed_observation') throw rendererFailure;
      }, caller.signal).then(() => null, error => error).then(error => { settled = true; return error; });
      try {
        await cancelling;
        // One event-loop turn drains promise reactions without a timing threshold.
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(requests.at(-1).options.method, 'DELETE');
        assert.equal(requests.at(-1).options.headers.Authorization, 'Bearer synthetic-token');
        assert.equal(requests.at(-1).options.signal.aborted, false);
        assert.equal(streamSignal.aborted, true);
        assert.equal(caller.signal.aborted, false);
        assert.equal(stream.locked, false);
        assert.equal(views.at(-1).label, 'expired');
        assert.equal(settled, true, 'underlying cancellation must not hold observer completion');
        const error = await observed;
        if (failureKind === 'parser') assert.equal(error?.message, 'invalid_event');
        else assert.equal(error, rendererFailure);
      } finally {
        release();
        await observed;
      }
    });
  }
}
