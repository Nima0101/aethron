import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {test} from 'node:test';
import {observe} from './dist/client.js';

const session = {session: 'a'.repeat(32), source_profile: 'bench'};
const reasons = [new Error('private_transport_marker', {cause: {token: 'private_cause_marker'}}),
  {address: 'private_endpoint_marker'}, 'private_string_marker'];

for (const phase of ['POST', 'GET', 'read']) {
  for (const [index, reason] of reasons.entries()) {
    test(`${phase} transport rejection ${index} exposes only a fixed phase error`, async t => {
      const requests = [], views = [];
      t.mock.method(globalThis, 'setInterval', () => 0);
      t.mock.method(globalThis, 'clearInterval', () => {});
      t.mock.method(globalThis, 'fetch', async (url, options) => {
        const method = options.method ?? 'GET';
        requests.push(method);
        if (method === phase) throw reason;
        if (method === 'POST') return Response.json(session);
        if (method === 'DELETE') return new Response(null, {status: 204});
        return new Response(new ReadableStream({start(controller) {controller.error(reason);}}));
      });
      const error = await observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => views.push(view),
        new AbortController().signal).then(() => undefined, error => error);
      assert.ok(error instanceof Error);
      assert.equal(error.message, phase === 'POST' ? 'session_unavailable' : 'stream_unavailable');
      assert.notEqual(error, reason);
      assert.equal(error.cause, undefined);
      assert.deepEqual(Object.keys(error), []);
      assert.deepEqual(requests, phase === 'POST' ? ['POST'] : ['POST', 'GET', 'DELETE']);
      if (phase !== 'POST') assert.equal(views.at(-1).label, 'expired');
    });
  }
}

for (const [phase, point, expected] of [
  ['POST', 'before', 'session_unavailable'],
  ['POST', 'headers', 'session_unavailable'],
  ['POST', 'body', 'invalid_session'],
  ['GET', 'headers', 'stream_unavailable'],
  ['GET', 'body', 'stream_unavailable'],
]) {
  test(`native caller cancellation during ${phase} ${point} keeps private reasons local`, async t => {
    const caller = new AbortController();
    const reason = new Error('private_abort_marker', {cause: {secret: 'private_cause_marker'}});
    const requests = [], views = [];
    const server = createServer((request, response) => {
      requests.push(request.method);
      request.resume();
      if (request.method === phase && point !== 'before') {
        if (point === 'headers') caller.abort(reason);
        else {response.writeHead(200); response.write('synthetic-stalled-body');}
      } else if (request.method === 'POST') response.end(JSON.stringify(session));
      else {response.writeHead(204); response.end();}
    });
    const nativeFetch = globalThis.fetch;
    // Real HTTP/fetch, with a deterministic abort immediately after the awaited
    // response headers. No arbitrary socket-delay assumption selects the phase.
    if (point === 'body') t.mock.method(globalThis, 'fetch', async (url, options) => {
      const response = await nativeFetch(url, options);
      if ((options.method ?? 'GET') === phase) caller.abort(reason);
      return response;
    });
    if (point === 'before') caller.abort(reason);
    let watchdog;
    try {
      await new Promise((resolve, reject) => {server.once('error', reject); server.listen(0, '127.0.0.1', resolve);});
      watchdog = setTimeout(() => {caller.abort(); server.closeAllConnections();}, 5000);
      const error = await observe(`http://127.0.0.1:${server.address().port}`, 'synthetic-token', 'bench',
        view => views.push(view), caller.signal).then(() => undefined, error => error);
      assert.ok(error instanceof Error);
      assert.equal(error.message, expected);
      assert.equal(error.cause, undefined);
      assert.notEqual(error, reason);
      assert.equal(caller.signal.reason, reason, 'caller retains ownership of its reason');
      assert.deepEqual(requests, point === 'before' ? [] : phase === 'POST' ? ['POST'] : ['POST', 'GET', 'DELETE']);
      if (phase === 'GET') assert.equal(views.at(-1).label, 'expired');
    } finally {
      clearTimeout(watchdog);
      server.closeAllConnections();
      if (server.listening) await new Promise(resolve => server.close(resolve));
    }
  });
}

for (const tail of ['scene', 'malformed']) {
  test(`caller abort in display stops before the same-chunk ${tail} tail`, async t => {
    const caller = new AbortController(), views = [], requests = [];
    const result = JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url))).results[0];
    const scene = {api_version: '1', kind: 'scene', sequence: 1, session: session.session,
      clock: {domain: 'edge_monotonic', emitted_ms: 0, valid_for_ms: 100}, result};
    const wire = value => `data: ${JSON.stringify(value)}\n\n`;
    const bytes = wire(scene) + (tail === 'scene' ? wire({...scene, sequence: 2}) : 'data: {bad}\n\n');
    t.mock.method(performance, 'now', () => 0);
    t.mock.method(globalThis, 'setInterval', () => 0);
    t.mock.method(globalThis, 'clearInterval', () => {});
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      const method = options.method ?? 'GET';
      requests.push(method);
      if (method === 'POST') return Response.json(session);
      if (method === 'DELETE') return new Response(null, {status: 204});
      return new Response(bytes);
    });
    const error = await observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => {
      views.push(view);
      if (view.label === 'delayed_observation') caller.abort(new Error('private_abort_marker'));
    }, caller.signal).then(() => undefined, error => error);
    assert.equal(views.filter(view => view.label === 'delayed_observation').length, 1);
    assert.equal(error?.message, 'stream_unavailable');
    assert.equal(views.at(-1).label, 'expired');
    assert.deepEqual(requests, ['POST', 'GET', 'DELETE']);
  });
}
