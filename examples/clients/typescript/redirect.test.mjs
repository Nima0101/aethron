import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {test} from 'node:test';
import {observe} from './dist/client.js';

const session = 'a'.repeat(32);
const reply = JSON.stringify({session, source_profile: 'bench'});

// Removing redirect rejection from any authenticated request must make its
// corresponding destination receive a request and fail these controls.
async function exercise(phase, status, crossOrigin = false) {
  const reached = [], destinations = [], views = [];
  let destinationBase;
  const destination = createServer((request, response) => {
    destinations.push({method: request.method, authorization: request.headers.authorization});
    request.resume();
    response.end(phase === 'POST' ? reply : '');
  });
  const server = createServer((request, response) => {
    request.resume();
    if (request.url === '/redirected') {
      destinations.push({method: request.method, authorization: request.headers.authorization});
      response.end(phase === 'POST' ? reply : '');
      return;
    }
    reached.push({method: request.method, url: request.url, authorization: request.headers.authorization});
    if (request.method === phase) {
      response.writeHead(status, {Location: crossOrigin ? `${destinationBase}/redirected` : '/redirected'});
      response.end();
    } else if (request.method === 'POST') {
      response.setHeader('Content-Type', 'application/json');
      response.end(reply);
    } else {
      response.end();
    }
  });
  async function listen(instance) {
    await new Promise((resolve, reject) => {
      instance.once('error', reject);
      instance.listen(0, '127.0.0.1', resolve);
    });
    return `http://127.0.0.1:${instance.address().port}`;
  }
  try {
    if (crossOrigin) destinationBase = await listen(destination);
    const base = await listen(server);
    const error = await observe(base, 'synthetic-token', 'bench', view => views.push(view),
      AbortSignal.timeout(2000)).then(() => null, error => error);
    return {error, reached, destinations, views};
  } finally {
    for (const instance of [server, destination]) {
      instance.closeAllConnections();
      if (instance.listening) await new Promise(resolve => instance.close(resolve));
    }
  }
}

for (const phase of ['POST', 'GET', 'DELETE']) {
  for (const status of [301, 302, 303, 307, 308]) {
    for (const crossOrigin of [false, true]) {
      test(`${phase} ${status} cannot redirect ${crossOrigin ? 'across origins' : 'within origin'}`, async () => {
        const {error, reached, destinations, views} = await exercise(phase, status, crossOrigin);
        assert.deepEqual(destinations, [], 'redirect destination must receive no request');
        assert.deepEqual(reached.map(request => request.method), phase === 'POST' ? ['POST'] : ['POST', 'GET', 'DELETE']);
        assert.ok(reached.every(request => request.authorization === 'Bearer synthetic-token'));
        if (phase === 'DELETE') assert.equal(error, null); // cleanup is best effort
        else assert.ok(error instanceof Error);
        if (phase !== 'POST') assert.equal(views.at(-1).label, 'expired');
      });
    }
  }
}

test('direct loopback requests still create, read and delete a viewer session', async () => {
  const {error, reached, destinations, views} = await exercise(undefined, undefined);
  assert.equal(error, null);
  assert.deepEqual(destinations, []);
  assert.deepEqual(reached.map(({method, url}) => [method, url]), [
    ['POST', '/api/v1/sessions'], ['GET', `/api/v1/sessions/${session}/events`],
    ['DELETE', `/api/v1/sessions/${session}`],
  ]);
  assert.equal(views.at(-1).label, 'expired');
  assert.ok(views.every(view => view.current_state === 'UNKNOWN'));
});
