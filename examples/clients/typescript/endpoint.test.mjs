import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {test} from 'node:test';
import {observe} from './dist/client.js';

const session = {session: 'a'.repeat(32), source_profile: 'bench'};
const rejected = [
  '', '/relative', '//example.test', 'example.test', 'not a URL',
  'http://example.test', 'http://192.0.2.1', 'http://localhost',
  'http://127.0.0.1.example.test', 'http://[::ffff:127.0.0.1]',
  'file:///tmp/private-marker', 'ftp://example.test', 'ws://127.0.0.1',
  'https://user:private-marker@example.test', 'https://user@example.test',
  'https://example.test/prefix', 'https://example.test//',
  'https://example.test?private-marker', 'https://example.test#private-marker',
  'https://example.test?', 'https://example.test#',
  ' https://example.test', 'https://example.test\n', 'https://exam\tple.test',
  'https:\\example.test', 'https://example.test\\',
  'https://example.test/../', 'http://127.1', 'http://2130706433',
  'http://0x7f000001', 'http://0177.0.0.1', 'https://EXAMPLE.test',
  'https://example.test:443', 'https://example.test:99999',
  null, undefined, 123, {toString() {throw new Error('private-marker');}},
];

for (const [index, base] of rejected.entries()) {
  test(`endpoint ${index} is rejected before credentials reach fetch`, async t => {
    const requests = [], views = [];
    t.mock.method(globalThis, 'setInterval', () => 0);
    t.mock.method(globalThis, 'clearInterval', () => {});
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      requests.push(url);
      if (options.method === 'POST') return Response.json(session);
      return new Response(null, {status: 204});
    });
    const error = await observe(base, 'synthetic-token', 'bench', view => views.push(view),
      new AbortController().signal).then(() => undefined, error => error);
    assert.deepEqual(requests, [], 'no endpoint rejection may send a request');
    assert.equal(error?.message, 'invalid_endpoint');
    assert.equal(error?.cause, undefined);
    assert.deepEqual(views, []);
  });
}

for (const base of ['http://127.0.0.1:8765', 'http://127.0.0.1:8765/',
  'http://[::1]:8765', 'http://[::1]:8765/', 'https://example.test',
  'https://example.test/', 'https://example.test:8443/']) {
  test(`admitted origin ${base} builds three exact authenticated routes`, async t => {
    const requests = [];
    t.mock.method(globalThis, 'setInterval', () => 0);
    t.mock.method(globalThis, 'clearInterval', () => {});
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      requests.push({url, method: options.method ?? 'GET'});
      assert.equal(options.headers.Authorization, 'Bearer synthetic-token');
      assert.equal(options.redirect, 'error');
      if (options.method === 'POST') return Response.json(session);
      return options.method === 'DELETE' ? new Response(null, {status: 204}) : new Response('');
    });
    await observe(base, 'synthetic-token', 'bench', () => {}, new AbortController().signal);
    const origin = new URL(base).origin;
    assert.deepEqual(requests, [
      {url: `${origin}/api/v1/sessions`, method: 'POST'},
      {url: `${origin}/api/v1/sessions/${session.session}/events`, method: 'GET'},
      {url: `${origin}/api/v1/sessions/${session.session}`, method: 'DELETE'},
    ]);
  });
}

for (const suffix of ['?private-marker', '#private-marker', '/']) {
  test(`native loopback endpoint suffix ${suffix} respects origin admission`, async () => {
    const requests = [], caller = new AbortController();
    const server = createServer((request, response) => {
      requests.push({url: request.url, method: request.method});
      request.resume();
      if (request.method === 'POST') response.end(JSON.stringify(session));
      else if (request.method === 'GET') response.end();
      else {response.writeHead(204); response.end();}
    });
    let watchdog;
    try {
      await new Promise((resolve, reject) => {server.once('error', reject); server.listen(0, '127.0.0.1', resolve);});
      watchdog = setTimeout(() => {caller.abort(); server.closeAllConnections();}, 5000);
      const error = await observe(`http://127.0.0.1:${server.address().port}${suffix}`, 'synthetic-token',
        'bench', () => {}, caller.signal).then(() => undefined, error => error);
      if (suffix === '/') {
        assert.equal(error, undefined);
        assert.deepEqual(requests, [
          {url: '/api/v1/sessions', method: 'POST'},
          {url: `/api/v1/sessions/${session.session}/events`, method: 'GET'},
          {url: `/api/v1/sessions/${session.session}`, method: 'DELETE'},
        ]);
      } else {
        assert.deepEqual(requests, []);
        assert.equal(error?.message, 'invalid_endpoint');
      }
    } finally {
      clearTimeout(watchdog); server.closeAllConnections();
      if (server.listening) await new Promise(resolve => server.close(resolve));
    }
  });
}
