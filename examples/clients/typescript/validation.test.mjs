import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {Ajv2020} from 'ajv/dist/2020.js';
import standalone from 'ajv/dist/standalone/index.js';
import generated from './dist/validators.cjs';

const schema = JSON.parse(readFileSync(new URL('./src/scene.schema.json', import.meta.url), 'utf8'));
const compiler = new Ajv2020({strict: true});
const original = [compiler.compile(schema), compiler.compile({...schema, $ref: '#/$defs/HealthEvent'})];
const migrated = [generated.validateScene, generated.validateHealth];
const result = JSON.parse(readFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url))).results[0];
const scene = {api_version: '1', kind: 'scene', sequence: 1, session: 'a'.repeat(32),
  clock: {domain: 'edge_monotonic', emitted_ms: 0, valid_for_ms: 100}, result};
const health = {api_version: '1', kind: 'health', sequence: 2, session: scene.session,
  reason: 'source_lost', scene_state: 'UNKNOWN', retryable: true};

function paths(value, prefix = []) {
  if (value === null || typeof value !== 'object') return [];
  return Object.keys(value).flatMap(key => [[...prefix, key], ...paths(value[key], [...prefix, key])]);
}

test('generated validators preserve strict admission across bounded mutations', t => {
  const seeds = [scene, health, {...health, kind: 'gap', reason: 'stream_gap'}];
  assert.equal(migrated[0](scene), true);
  assert.equal(migrated[1](health), true);
  assert.equal(migrated[1](seeds[2]), true);
  assert.equal(migrated[0]({...scene, person_identity: 'forbidden'}), false);
  let count = 0;
  const check = value => {
    for (let i = 0; i < original.length; i++) {
      const before = structuredClone(value);
      assert.equal(migrated[i](value), original[i](value), `admission differs for case ${count}, validator ${i}`);
      assert.deepEqual(value, before, 'validation must not coerce or mutate input');
    }
    count++;
  };
  for (const value of [null, true, 0, '', [], {}, ...seeds]) check(value);
  for (const seed of seeds) {
    for (const path of paths(seed)) {
      for (const replacement of [undefined, null, true, -1, 1.5, NaN, Infinity, '', 'UNKNOWN', [], {}]) {
        const value = structuredClone(seed);
        const parent = path.slice(0, -1).reduce((item, key) => item[key], value);
        if (replacement === undefined) delete parent[path.at(-1)];
        else parent[path.at(-1)] = replacement;
        check(value);
      }
    }
  }
  // JSON Schema counts Unicode code points, not UTF-16 code units.
  for (const length of [64, 65]) {
    const value = structuredClone(scene);
    value.result.tracks[0].id = '😀'.repeat(length);
    check(value);
    assert.equal(migrated[0](value), length === 64);
  }
  assert.ok(count < 2000, 'keep this deterministic corpus bounded');
  t.diagnostic(`${count} cases compared against both original validators`);
});

test('built validators exactly match the bundled versioned schema', () => {
  const ajv = new Ajv2020({strict: true, code: {source: true}});
  ajv.addSchema(schema, 'scene');
  ajv.addSchema({...schema, $ref: '#/$defs/HealthEvent'}, 'health');
  assert.equal(readFileSync(new URL('./dist/validators.cjs', import.meta.url), 'utf8'),
    standalone(ajv, {validateScene: 'scene', validateHealth: 'health'}));
});

test('built client loads without runtime string compilation', () => {
  const child = spawnSync(process.execPath, [
    '--disallow-code-generation-from-strings', '--input-type=module',
    '-e', "await import('./dist/client.js');",
  ], {cwd: new URL('.', import.meta.url), encoding: 'utf8', timeout: 10000});
  assert.equal(child.error, undefined);
  // Do not echo compiler output: it may contain schema or input contents.
  assert.equal(child.status, 0, 'client must load with string compilation disabled');
});

test('independent safety cases reject authority, identity and nonfinite inputs', t => {
  const mutations = [
    value => { value.api_version = '2'; },
    value => { value.sequence = Number.MAX_SAFE_INTEGER + 1; },
    value => { value.sequence = true; },
    value => { value.clock.valid_for_ms = 101; },
    value => { value.clock.valid_for_ms = '100'; },
    value => { value.result.recommendation.requires_independent_controller = false; },
    value => { value.result.recommendation.action = 'ENGAGE'; },
    value => { value.result.tracks[0].person_identity = 'synthetic-forbidden'; },
    value => { value.result.tracks[0].appearance_embedding = [0]; },
    value => { value.result.tracks[0].prediction = {centre: [0.5, 0.5], horizon_ms: 200, evidence: true}; },
    value => { value.result.tracks[0].covariance = [Infinity, 0]; },
    value => { value.result.tracks[0].covariance = [NaN, 0]; },
    value => { value.result.tracks = Array.from({length: 33}, () => structuredClone(value.result.tracks[0])); },
  ];
  for (const mutate of mutations) {
    const value = structuredClone(scene);
    mutate(value);
    const before = structuredClone(value);
    assert.equal(generated.validateScene(value), false);
    assert.deepEqual(value, before);
  }
  assert.equal(generated.validateHealth({...health, scene_state: 'PRESENT'}), false);
  t.diagnostic(`${mutations.length + 1} independent negative safety cases; no baseline validator oracle`);
});
