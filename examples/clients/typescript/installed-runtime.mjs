// Copied into an external temporary project by package.test.mjs; no source imports.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {Observation} from 'aethron-edge-client-example';

const fixture = JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url), 'utf8'));
const result = fixture.results[0];
assert.ok(result.tracks.length > 0, 'fixture must exercise non-empty observations');
const envelope = {api_version: '1', kind: 'scene', sequence: 1, session: 'a'.repeat(32),
  clock: {domain: 'edge_monotonic', emitted_ms: 0, valid_for_ms: 100}, result};
const observation = new Observation();
const expired = {label: 'expired', current_state: 'UNKNOWN', observed_state: 'UNKNOWN',
  sources: [], uncertainty: []};
assert.deepEqual(observation.view(0), expired);
observation.accept(envelope, 0);
const expected = {label: 'delayed_observation', current_state: 'UNKNOWN',
  observed_state: result.state, sources: [...new Set(result.tracks.flatMap(track => track.sources))],
  uncertainty: result.tracks.map(track => [...track.covariance])};
assert.deepEqual(observation.view(100), expected);
const mutable = observation.view(100);
mutable.sources.length = 0;
mutable.uncertainty[0][0] = 999;
assert.deepEqual(observation.view(100), expected);
assert.deepEqual(observation.view(101), expired);
observation.accept(envelope, 200);
assert.throws(() => observation.accept({...envelope, unexpected: true}, 200), {message: 'invalid_event'});
assert.deepEqual(observation.view(200), expired);
observation.accept(envelope, 300);
observation.disconnect();
assert.deepEqual(observation.view(300), expired);
await assert.rejects(import('aethron-edge-client-example/dist/wire.js'), {code: 'ERR_PACKAGE_PATH_NOT_EXPORTED'});
console.log(JSON.stringify({checks: 8, current_state: 'UNKNOWN'}));
