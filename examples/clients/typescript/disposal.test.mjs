import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {test} from 'node:test';
import {observe} from './dist/client.js';

const handle = 'a'.repeat(32);
const session = {session: handle, source_profile: 'bench'};
const phases = [
  ['POST', 503, 'session_unavailable'],
  ['GET', 503, 'stream_unavailable'],
  ['DELETE', 200, undefined],
  ['DELETE', 503, undefined],
];

for (const [phase, status, expectedError] of phases) {
  for (const mode of ['pending', 'rejected']) {
    test(`${phase} ${status} discards its unused body with ${mode} source cleanup`, async t => {
      let cancelled = 0, release, settled = false;
      const cleanup = new Promise(resolve => { release = resolve; });
      const body = new ReadableStream({cancel() {
        cancelled++;
        if (mode === 'rejected') throw new Error('private_cleanup_marker');
        return cleanup;
      }}, {highWaterMark: 0});
      const requests = [], views = [];
      t.mock.method(globalThis, 'setInterval', () => 0);
      t.mock.method(globalThis, 'clearInterval', () => {});
      t.mock.method(globalThis, 'fetch', async (url, options) => {
        const method = options.method ?? 'GET';
        requests.push(method);
        if (method === phase) return new Response(body, {status});
        if (method === 'POST') return Response.json(session);
        return options.method === 'DELETE' ? new Response(null, {status: 204}) : new Response('');
      });
      const observed = observe('http://127.0.0.1:8765', 'synthetic-token', 'bench',
        view => views.push(view), new AbortController().signal)
        .then(() => undefined, error => error).then(error => {settled = true; return error;});
      try {
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(cancelled, 1, 'unused response body must be cancelled exactly once');
        assert.equal(settled, true, 'source cleanup must not hold observer completion');
        assert.equal((await observed)?.message, expectedError);
        assert.deepEqual(requests, phase === 'POST' ? ['POST'] : ['POST', 'GET', 'DELETE']);
        assert.equal(body.locked, false);
        if (phase !== 'POST') assert.equal(views.at(-1).label, 'expired');
      } finally {
        release();
        await observed;
      }
    });
  }
}

for (const phase of ['POST', 'GET', 'DELETE']) {
  test(`${phase} accepts absent discard body without replacing the primary result`, async t => {
    t.mock.method(globalThis, 'setInterval', () => 0);
    t.mock.method(globalThis, 'clearInterval', () => {});
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      if ((options.method ?? 'GET') === phase) return new Response(null, {status: phase === 'DELETE' ? 204 : 503});
      if (options.method === 'POST') return Response.json(session);
      return options.method === 'DELETE' ? new Response(null, {status: 204}) : new Response('');
    });
    const error = await observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', () => {},
      new AbortController().signal).then(() => undefined, error => error);
    assert.equal(error?.message, phase === 'POST' ? 'session_unavailable' : phase === 'GET' ? 'stream_unavailable' : undefined);
  });
}

for (const phase of ['POST', 'GET', 'DELETE']) {
  test(`native fetch cancels the stalled unused ${phase} response`, async () => {
    let closed, timeout;
    const closure = new Promise(resolve => {closed = resolve;});
    const server = createServer((request, response) => {
      request.resume();
      if (request.method === phase) {
        response.on('close', () => closed(true));
        response.writeHead(phase === 'DELETE' ? 200 : 503);
        response.write('synthetic-unused-body');
        // Deliberately no EOF. The client must cancel rather than drain.
      } else if (request.method === 'POST') {
        response.end(JSON.stringify(session));
      } else response.end();
    });
    try {
      await new Promise((resolve, reject) => {server.once('error', reject); server.listen(0, '127.0.0.1', resolve);});
      const base = `http://127.0.0.1:${server.address().port}`;
      const error = await observe(base, 'synthetic-token', 'bench', () => {}, AbortSignal.timeout(10000))
        .then(() => undefined, error => error);
      assert.equal(error?.message, phase === 'POST' ? 'session_unavailable' : phase === 'GET' ? 'stream_unavailable' : undefined);
      // Bounded test timeout, not a production latency promise. It is shorter
      // than request abort deadlines, which otherwise could conceal the leak.
      const disposed = await Promise.race([closure, new Promise(resolve => {timeout = setTimeout(() => resolve(false), 1000);})]);
      assert.equal(disposed, true, 'unused HTTP response must close before the request timeout');
    } finally {
      clearTimeout(timeout);
      server.closeAllConnections();
      if (server.listening) await new Promise(resolve => server.close(resolve));
    }
  });
}
