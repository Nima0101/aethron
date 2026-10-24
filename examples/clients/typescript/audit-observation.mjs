// Bounded, synthetic technology comparison. No network or persistent scene log.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {Observation} from './dist/client.js';
import validators from './dist/validators.cjs';

const fixture = JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url)));
const envelope = {api_version: '1', kind: 'scene', sequence: 1, session: 'a'.repeat(32),
  clock: {domain: 'edge_monotonic', emitted_ms: 0, valid_for_ms: 100}, result: fixture.results[0]};
const expired = () => ({label: 'expired', current_state: 'UNKNOWN', observed_state: 'UNKNOWN', sources: [], uncertainty: []});

// JS transcription of Observation at bb36aafe, retaining its full-scene strategy
// and its known property/reflection shortcomings. Never import into production.
class Legacy {
  scene = null; received = 0; lastViewed = 0;
  accept(value, now) {
    this.disconnect();
    if (!Number.isFinite(now) || now < 0) throw new Error('invalid_clock');
    let snapshot;
    try { snapshot = structuredClone(value); } catch { throw new Error('invalid_event'); }
    if (!validators.validateScene(snapshot)) throw new Error('invalid_event');
    this.scene = snapshot; this.received = now; this.lastViewed = now;
  }
  disconnect() { this.scene = null; }
  view(now) {
    if (!this.scene || !Number.isFinite(now) || now < 0 || now < this.lastViewed ||
        now - this.received > this.scene.clock.valid_for_ms) { this.disconnect(); return expired(); }
    this.lastViewed = now;
    return {label: 'delayed_observation', current_state: 'UNKNOWN', observed_state: this.scene.result.state,
      sources: [...new Set(this.scene.result.tracks.flatMap(t => t.sources))],
      uncertainty: this.scene.result.tracks.map(t => [...t.covariance])};
  }
}

// A host-language alternative with equally hidden state, but per-instance methods.
function closureObservation() {
  let projection = null, received = 0, lastViewed = 0;
  const disconnect = () => { projection = null; received = 0; lastViewed = 0; };
  return {
    disconnect,
    accept(value, now) {
      disconnect();
      if (!Number.isFinite(now) || now < 0) throw new Error('invalid_clock');
      let snapshot;
      try {
        snapshot = structuredClone(value);
        if (!validators.validateScene(snapshot)) throw new Error('invalid_event');
      } catch { disconnect(); throw new Error('invalid_event'); }
      projection = {validForMs: snapshot.clock.valid_for_ms, observedState: snapshot.result.state,
        sources: [...new Set(snapshot.result.tracks.flatMap(t => t.sources))],
        uncertainty: snapshot.result.tracks.map(t => [...t.covariance])};
      received = now; lastViewed = now;
    },
    view(now) {
      if (!projection || !Number.isFinite(now) || now < 0 || now < lastViewed ||
          now - received > projection.validForMs) { disconnect(); return expired(); }
      lastViewed = now;
      return {label: 'delayed_observation', current_state: 'UNKNOWN', observed_state: projection.observedState,
        sources: [...projection.sources], uncertainty: projection.uncertainty.map(row => [...row])};
    },
  };
}

const strategies = {legacy: () => new Legacy(), closure: closureObservation, native_private: () => new Observation()};
let traces = 0, views = 0;
for (const receipt of [0, 0.5, 1000]) {
  for (const lease of [1, 50, 100]) {
    for (const offsets of [[0, lease / 2, lease, lease + 0.5, 0], [0, 0.75, 0.5, 1],
      [0, NaN, 0], [0, Infinity, 0], [0, -1, 0]]) {
      const input = {...envelope, clock: {...envelope.clock, valid_for_ms: lease}};
      const clients = Object.values(strategies).map(make => make());
      clients.forEach(client => client.accept(input, receipt));
      input.clock.valid_for_ms = 1000; // cannot mutate a previously accepted lease
      for (const offset of offsets) {
        const [reference, ...candidates] = clients.map(client => client.view(receipt + offset));
        candidates.forEach(value => assert.deepEqual(value, reference));
        assert.equal(reference.current_state, 'UNKNOWN'); views++;
      }
      clients.forEach(client => { client.disconnect(); assert.deepEqual(client.view(receipt), expired()); });
      traces++;
    }
  }
}
for (const name of ['closure', 'native_private']) {
  const candidate = strategies[name](); candidate.accept(envelope, 0);
  assert.equal(JSON.stringify(candidate), '{}');
  candidate.received = 50;
  assert.equal(candidate.view(101).label, 'expired');
}
assert.equal(strategies.native_private().view, strategies.native_private().view);
assert.notEqual(strategies.closure().view, strategies.closure().view);

const report = {node: process.version, platform: process.platform, arch: process.arch,
  parity_traces: traces, parity_views: views,
  parity_scope: 'Plain-data timing/copy traces only; legacy and closure prototypes do not implement current reentrant admission revocation.',
  legacy_exceptions: 'Historical ownership and later reentrant admission corrections are covered by test.mjs, not this parity comparison.',
  cycles_per_round: 100, views_per_cycle: 20, tracks: 32, measurements: [], sha256: {}};
const full = structuredClone(envelope);
full.result.tracks = Array.from({length: 32}, (_, i) => ({...structuredClone(envelope.result.tracks[0]), id: `synthetic-${i}`}));
assert.equal(validators.validateScene(full), true);
for (let round = 0; round < (process.argv.includes('--check') ? 0 : 3); round++) {
  for (const name of round % 2 ? Object.keys(strategies).reverse() : Object.keys(strategies)) {
    const start = performance.now(); let samples = 0;
    for (let cycle = 0; cycle < report.cycles_per_round; cycle++) {
      const client = strategies[name](); client.accept(full, 0);
      for (let tick = 0; tick < report.views_per_cycle; tick++) {
        const view = client.view(tick);
        assert.equal(view.label, 'delayed_observation'); samples += view.uncertainty.length;
      }
      client.disconnect();
    }
    report.measurements.push({round, strategy: name, elapsed_ms: performance.now() - start, covariance_rows: samples});
  }
}
for (const path of ['src/client.ts', 'dist/client.js', 'audit-observation.mjs', 'src/scene.schema.json']) {
  report.sha256[path] = createHash('sha256').update(readFileSync(new URL(path, import.meta.url))).digest('hex');
}
console.log(JSON.stringify(report, null, 2));
