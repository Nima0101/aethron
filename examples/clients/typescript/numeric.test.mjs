import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {observe} from './dist/client.js';

const result = JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url))).results[0];
const seed = {api_version: '1', kind: 'scene', sequence: 1, session: 'a'.repeat(32),
  clock: {domain: 'edge_monotonic', emitted_ms: 0, valid_for_ms: 100}, result};
seed.result.tracks[0].prediction = {centre: [0.5, 0.5], horizon_ms: 200, evidence: false};
async function consume(t, json) {
  const views = [], requests = [];
  t.mock.method(performance, 'now', () => 0);
  t.mock.method(globalThis, 'setInterval', () => 0);
  t.mock.method(globalThis, 'clearInterval', () => {});
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push(options.method ?? 'GET');
    if (options.method === 'POST') return Response.json({session: seed.session, source_profile: 'bench'});
    if (options.method === 'DELETE') return new Response(null, {status: 204});
    return new Response(`data: ${json}\n\n`);
  });
  const error = await observe('http://127.0.0.1:8765', 'synthetic-token', 'bench', view => views.push(view),
    new AbortController().signal).then(() => undefined, error => error);
  assert.deepEqual(requests, ['POST', 'GET', 'DELETE']);
  assert.equal(views.at(-1).label, 'expired');
  return {error, observations: views.filter(view => view.label === 'delayed_observation')};
}
const paths = [
  ['sequence'], ['clock', 'emitted_ms'], ['clock', 'valid_for_ms'],
  ['result', 'version'], ['result', 'at_ms'], ['result', 'expires_at_ms'],
  ['result', 'tracks', 0, 'freshness_ms'], ['result', 'tracks', 0, 'expires_at_ms'],
  ['result', 'tracks', 0, 'prediction', 'horizon_ms'],
];
for (const path of paths) {
  for (const suffix of ['.0', 'e0', '.00000000000000001']) {
    test(`wire integer ${path.join('.')} rejects numeric spelling ${suffix}`, async t => {
      const value = structuredClone(seed);
      const parent = path.slice(0, -1).reduce((node, key) => node[key], value), key = path.at(-1);
      const token = String(parent[key]) + suffix;
      parent[key] = 'WIRE_NUMBER';
      const {error, observations} = await consume(t, JSON.stringify(value).replace('"WIRE_NUMBER"', token));
      assert.equal(error?.message, 'invalid_event');
      assert.equal(error?.cause, undefined);
      assert.equal(observations.length, 0);
    });
  }
}
for (const kind of ['health', 'gap']) {
  test(`${kind} sequence rejects exponent spelling`, async t => {
    const value = {api_version: '1', kind, sequence: 'WIRE_NUMBER', session: seed.session,
      reason: 'source_lost', scene_state: 'UNKNOWN', retryable: true};
    const {error} = await consume(t, JSON.stringify(value).replace('"WIRE_NUMBER"', '1e0'));
    assert.equal(error?.message, 'invalid_event');
  });
}
test('escaped integer property cannot bypass lexical admission', async t => {
  const {error} = await consume(t, JSON.stringify(seed).replace('"sequence":1', '"\\u0073equence":1.0'));
  assert.equal(error?.message, 'invalid_event');
});
for (const [name, transform] of [
  ['ordinary integer tokens', json => json],
  ['maximum safe sequence', json => json.replace('"sequence":1', '"sequence":9007199254740991')],
  ['negative zero integer', json => json.replace('"emitted_ms":0', '"emitted_ms":-0')],
  ['decimal and exponent geometry', json => json.replace('"centre":[0.5,0.5]', '"centre":[0.50,5e-1]')],
  ['numeric-looking reason text', json => {const value = JSON.parse(json); value.result.reasons = ['sequence: 1.0']; return JSON.stringify(value);}],
]) {
  test(`wire preserves ${name}`, async t => {
    const {error, observations} = await consume(t, transform(JSON.stringify(seed)));
    assert.equal(error, undefined);
    assert.equal(observations.length, 1);
  });
}

test('missing source-aware parsing fails closed for integer wire fields', async t => {
  const parse = JSON.parse;
  t.mock.method(JSON, 'parse', (text, reviver) => parse(text, reviver && ((key, value) => reviver(key, value))));
  const {error, observations} = await consume(t, JSON.stringify(seed));
  assert.equal(error?.message, 'invalid_event');
  assert.equal(observations.length, 0);
});
