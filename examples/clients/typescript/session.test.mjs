import assert from 'node:assert/strict';
import {test} from 'node:test';
import {observe} from './dist/client.js';

const handle = 'a'.repeat(32);
const valid = JSON.stringify({session: handle, source_profile: 'bench'});
const encode = text => new TextEncoder().encode(text);
async function consume(t, response) {
  const requests = [], views = [];
  t.mock.method(globalThis, 'setInterval', () => 0);
  t.mock.method(globalThis, 'clearInterval', () => {});
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({url, options});
    if (options.method === 'POST') return response;
    if (options.method === 'DELETE') return new Response(null, {status: 204});
    return new Response('');
  });
  const error = await observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => views.push(view),
    new AbortController().signal).then(() => null, error => error);
  return {error, requests, views};
}

for (const [name, body] of [
  ['missing profile', JSON.stringify({session: handle})],
  ['wrong profile', JSON.stringify({session: handle, source_profile: 'other'})],
  ['extra field', JSON.stringify({session: handle, source_profile: 'bench', identity: 'forbidden'})],
  ['duplicate handle', `{"session":"${'b'.repeat(32)}",${valid.slice(1)}`],
  ['escaped duplicate profile', valid.replace('"source_profile":', '"\\u0073ource_profile":"other","source_profile":')],
  ['malformed private input', '{"private_session_marker":}'],
  ['null root', 'null'],
  ['array root', `[${valid}]`],
  ['invalid handle', valid.replace(handle, '../private_session_marker')],
  ['BOM prefix', '\ufeff' + valid],
  ['oversized body', ' '.repeat(65537 - encode(valid).length) + valid],
]) {
  test(`session rejects ${name} before using any returned handle`, async t => {
    const {error, requests, views} = await consume(t, new Response(body));
    assert.equal(error?.message, 'invalid_session');
    assert.equal(requests.length, 1);
    assert.equal(views.length, 0);
  });
}
test('null response body rejects with a fixed session error', async t => {
  const {error, requests} = await consume(t, new Response(null, {status: 204}));
  assert.equal(error?.message, 'invalid_session');
  assert.equal(requests.length, 1);
});
test('valid session at the local inclusive byte limit is admitted', async t => {
  const {error, requests} = await consume(t, new Response(' '.repeat(65536 - encode(valid).length) + valid));
  assert.equal(error, null);
  assert.equal(requests.length, 3);
  assert.equal(requests.at(-1).options.method, 'DELETE');
});
test('one-byte session chunks preserve complete schema validation', async t => {
  const bytes = encode(valid); let index = 0;
  const stream = new ReadableStream({pull(controller) {
    if (index < bytes.length) controller.enqueue(bytes.slice(index, ++index));
    else controller.close();
  }});
  const {error} = await consume(t, new Response(stream));
  assert.equal(error, null);
  assert.equal(stream.locked, false);
});
test('session body read failure cannot echo transport details', async t => {
  const stream = new ReadableStream({start(controller) {controller.error(new Error('private_transport_marker'));}});
  const {error, requests} = await consume(t, new Response(stream));
  assert.equal(error?.message, 'invalid_session');
  assert.equal(requests.length, 1);
  assert.equal(stream.locked, false);
});
test('oversized session cancels without waiting for source cleanup', async t => {
  let release, finish, cancelled = false, settled = false;
  const cleanup = new Promise(resolve => { release = resolve; });
  const stream = new ReadableStream({
    start(controller) {finish = () => controller.close(); controller.enqueue(encode(' '.repeat(65537) + valid));},
    cancel() {cancelled = true; return cleanup;},
  });
  const observed = consume(t, new Response(stream)).then(result => {settled = true; return result;});
  try {
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(settled, true);
    const {error, requests} = await observed;
    assert.equal(error?.message, 'invalid_session');
    assert.equal(requests.length, 1);
    assert.equal(cancelled, true);
    assert.equal(stream.locked, false);
  } finally {
    // Also lets the baseline's unbounded reader finish after the failed assertion.
    release();
    if (!cancelled) finish();
    await observed;
  }
});
