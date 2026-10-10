import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {test} from 'node:test';
import {observe} from './dist/client.js';

const session = {session: 'a'.repeat(32), source_profile: 'bench'};
const reasons = [new Error('private_transport_marker', {cause: {token: 'private_cause_marker'}}),
  {address: 'private_endpoint_marker'}, 'private_string_marker'];

for (const component of ['observer-setup', 'observer-revocation', 'render-publication']) test(`${component} decision uses a closed schema and four architecture views`, async () => {
  const {Ajv2020} = await import('ajv/dist/2020.js');
  const read = name => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
  const validate = new Ajv2020({strict:true}).compile(read(`./${component}-adr.schema.json`));
  const adr = read(`./${component}-adr.json`);
  assert.equal(validate(adr), true, JSON.stringify(validate.errors));
  assert.equal(validate({...adr, qualified:true}), false);
  assert.equal(validate({...adr, c4:{...adr.c4, unreviewed:'claim'}}), false);
});

for (const phase of ['controller', 'signal-composition', 'scheduler']) {
  for (const displayFails of [false, true]) {
    test(`${phase} setup failure withdraws display and releases the admitted handle (display failure=${displayFails})`, async t => {
      const requests = [], views = [], cleared = [];
      const privateFailure = new Error('private_setup_marker');
      const displayFailure = new Error('application_display_failure');
      const caller = new AbortController();
      const admittedResponse = Response.json(session);
      const deletedResponse = new Response(null, {status:204});
      if (phase === 'controller') t.mock.method(globalThis, 'AbortController', function () {throw privateFailure;});
      t.mock.method(globalThis, 'setInterval', () => {
        if (phase === 'scheduler') throw privateFailure;
        assert.fail('no timer should start after signal composition fails');
      });
      t.mock.method(globalThis, 'clearInterval', timer => cleared.push(timer));
      if (phase === 'signal-composition') t.mock.method(AbortSignal, 'any', () => {throw privateFailure;});
      t.mock.method(globalThis, 'fetch', async (url, options) => {
        requests.push({url, options});
        if (options.method === 'POST') return admittedResponse;
        assert.equal(options.method, 'DELETE', 'setup failure must not start event reception');
        return deletedResponse;
      });
      const error = await observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => {
        views.push(view);if (displayFails) throw displayFailure;
      }, caller.signal).then(() => undefined, error => error);
      assert.deepEqual(requests.map(request => request.options.method), ['POST', 'DELETE']);
      assert.equal(views.length, 1);assert.equal(views[0].label, 'expired');
      assert.deepEqual(views[0].sources, []);assert.deepEqual(cleared, []);
      assert.notEqual(requests[1].options.signal, caller.signal);
      assert.equal(requests[1].options.redirect, 'error');
      if (displayFails) assert.equal(error, displayFailure);
      else {assert.equal(error?.message, 'stream_unavailable');assert.equal(error.cause, undefined);}
    });
  }
}

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

for (const point of ['pending-read', 'display-callback']) {
  test(`timer withdraws a cancelled observation before ${point} unwinds`, async t => {
    const caller = new AbortController(), views = [], requests = [];
    let tick, controller, admitted;
    const ready = new Promise(resolve => {admitted = resolve;});
    const result = JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url))).results[0];
    const scene = {api_version:'1', kind:'scene', sequence:1, session:session.session,
      clock:{domain:'edge_monotonic', emitted_ms:0, valid_for_ms:100}, result};
    t.mock.method(performance, 'now', () => 0);
    t.mock.method(globalThis, 'setInterval', callback => {tick = callback;return 0;});
    t.mock.method(globalThis, 'clearInterval', () => {});
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      requests.push(options.method ?? 'GET');
      if (options.method === 'POST') return Response.json(session);
      if (options.method === 'DELETE') return new Response(null, {status:204});
      // Deliberately keep read pending until the test releases it. Withdrawal
      // must follow the abort state, not await a transport promise reaction.
      return new Response(new ReadableStream({start(value) {
        controller = value;
        value.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(scene)}\n\n`));
      }}));
    });
    let nested = false;
    const observed = observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => {
      views.push(view);
      if (view.label === 'delayed_observation' && !nested) {
        nested = true;
        if (point === 'display-callback') {
          caller.abort(new Error('private_abort_marker'));tick();
        }
        admitted();
      }
    }, caller.signal).then(() => undefined, error => error);
    try {
      await ready;
      if (point === 'pending-read') {caller.abort(new Error('private_abort_marker'));tick();}
      assert.equal(views.at(-1).label, 'expired');
      assert.deepEqual(views.at(-1).sources, []);
      assert.equal(views.filter(view => view.label === 'delayed_observation').length, 1);
    } finally {
      if (point === 'pending-read') controller.close();
      assert.equal((await observed)?.message, 'stream_unavailable');
      assert.equal(requests.at(-1), 'DELETE');
    }
  });
}

for (const ending of ['EOF', 'invalid-event']) {
  test(`retained timer callback is inert after ${ending} termination`, async t => {
    let tick;
    const views = [];
    t.mock.method(globalThis, 'setInterval', callback => {tick = callback;return 0;});
    t.mock.method(globalThis, 'clearInterval', () => {});
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      if (options.method === 'POST') return Response.json(session);
      if (options.method === 'DELETE') return new Response(null, {status:204});
      return new Response(ending === 'EOF' ? '' : 'data: {bad}\n\n');
    });
    const error = await observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => views.push(view),
      new AbortController().signal).then(() => undefined, error => error);
    assert.equal(error?.message, ending === 'EOF' ? undefined : 'invalid_event');
    assert.equal(views.at(-1).label, 'expired');
    const count = views.length;
    tick();tick();
    assert.equal(views.length, count, 'a retired observer must not invoke its display again');
  });
}

test('native fetch cancellation withdraws before its read rejection is handled', async t => {
  const caller = new AbortController(), views = [], requests = [];
  let tick, admitted, watchdog;
  const ready = new Promise(resolve => {admitted = resolve;});
  const result = JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url))).results[0];
  const scene = {api_version:'1', kind:'scene', sequence:1, session:session.session,
    clock:{domain:'edge_monotonic', emitted_ms:0, valid_for_ms:100}, result};
  t.mock.method(performance, 'now', () => 0);
  t.mock.method(globalThis, 'setInterval', callback => {tick = callback;return 0;});
  t.mock.method(globalThis, 'clearInterval', () => {});
  const server = createServer((request, response) => {
    requests.push(request.method);request.resume();
    if (request.method === 'POST') response.end(JSON.stringify(session));
    else if (request.method === 'DELETE') {response.writeHead(204);response.end();}
    else {response.writeHead(200);response.write(`data: ${JSON.stringify(scene)}\n\n`);}
  });
  let observed;
  try {
    await new Promise((resolve, reject) => {server.once('error', reject);server.listen(0, '127.0.0.1', resolve);});
    watchdog = setTimeout(() => {admitted();caller.abort();server.closeAllConnections();}, 5000);
    observed = observe(`http://127.0.0.1:${server.address().port}`, 'synthetic-token', 'bench', view => {
      views.push(view);if (view.label === 'delayed_observation') admitted();
    }, caller.signal).then(() => undefined, error => error);
    await ready;
    assert.equal(views.at(-1)?.label, 'delayed_observation');
    caller.abort(new Error('private_abort_marker'));
    // No await: native fetch rejection has not resumed the observer yet.
    tick();
    assert.equal(views.at(-1).label, 'expired');
    assert.deepEqual(views.at(-1).sources, []);
    assert.equal((await observed)?.message, 'stream_unavailable');
    assert.deepEqual(requests, ['POST', 'GET', 'DELETE']);
    const count = views.length;tick();assert.equal(views.length, count);
  } finally {
    clearTimeout(watchdog);caller.abort();server.closeAllConnections();
    await observed;
    if (server.listening) await new Promise(resolve => server.close(resolve));
  }
});

test('timer is retired before independent remote deletion settles', async t => {
  let tick, deleting, release;
  const ready = new Promise(resolve => {deleting = resolve;});
  const deletion = new Promise(resolve => {release = resolve;});
  const views = [];
  t.mock.method(globalThis, 'setInterval', callback => {tick = callback;return 0;});
  t.mock.method(globalThis, 'clearInterval', () => {});
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (options.method === 'POST') return Response.json(session);
    if (options.method === 'DELETE') {deleting();return deletion;}
    return new Response('');
  });
  const observed = observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => views.push(view),
    new AbortController().signal);
  try {
    await ready;
    assert.equal(views.at(-1).label, 'expired');
    const count = views.length;tick();assert.equal(views.length, count);
  } finally {release(new Response(null, {status:204}));await observed;}
});

for (const point of ['admission-clock', 'stream-view-clock', 'timer-view-clock']) {
  test(`callback publication rechecks cancellation after ${point}`, async t => {
    const caller = new AbortController(), views = [], requests = [];
    let tick, controller, armed = false, reads = 0;
    const result = JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url))).results[0];
    const scene = {api_version:'1', kind:'scene', sequence:1, session:session.session,
      clock:{domain:'edge_monotonic', emitted_ms:0, valid_for_ms:100}, result};
    const body = new ReadableStream({start(value) {
      controller = value;
      value.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(scene)}\n\n`));
    }});
    const response = new Response(body);
    t.mock.method(performance, 'now', () => {
      if (armed && ++reads === (point === 'stream-view-clock' ? 2 : 1)) {
        caller.abort(new Error('private_clock_abort_marker'));
      }
      return 0;
    });
    t.mock.method(globalThis, 'setInterval', callback => {tick = callback;return 0;});
    t.mock.method(globalThis, 'clearInterval', () => {});
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      requests.push(options.method ?? 'GET');
      if (options.method === 'POST') return Response.json(session);
      if (options.method === 'DELETE') return new Response(null, {status:204});
      armed = point !== 'timer-view-clock';
      return response;
    });
    const observed = observe('http://127.0.0.1:8765', 'synthetic-token', 'bench',
      view => views.push(view), caller.signal).then(() => undefined, error => error);
    try {
      await new Promise(resolve => setImmediate(resolve));
      if (point === 'timer-view-clock') {
        assert.equal(views.at(-1)?.label, 'delayed_observation');
        armed = true;reads = 0;tick();
      }
      assert.equal(caller.signal.aborted, true, 'fault injection must reach a clock read');
      assert.equal(views.filter(view => view.label === 'delayed_observation').length,
        point === 'timer-view-clock' ? 1 : 0, 'no cancelled projection may reach display');
      assert.equal(views.at(-1)?.label, 'expired');
      assert.deepEqual(views.at(-1).sources, []);
    } finally {
      if (body.locked) controller.close();
      const error = await observed;
      assert.equal(error?.message, 'stream_unavailable');
      assert.equal(error.cause, undefined);
      assert.deepEqual(requests, ['POST', 'GET', 'DELETE']);
    }
  });
}
