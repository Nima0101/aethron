// Bounded audit probe; sequential children only. Run after npm run build.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

const args = process.argv.slice(2);
assert.ok(args.length === 0 || (args.length === 1 && args[0] === '--check'), 'expected_optional_check');
const checkOnly = args.length === 1;
const result = {node: process.version, platform: process.platform, arch: process.arch,
  mode: checkOnly ? 'correctness-only' : 'shared-host-benchmark',
  scope: 'Same three validators; shared AJV implementation, not an independent correctness oracle or hardware qualification.',
  rounds: checkOnly ? 1 : 3, warm_iterations: checkOnly ? 0 : 10000,
  checks: [], measurements: [], sha256: {}, generated_bytes: 0};
for (const path of ['src/scene.schema.json', 'generate-validators.mjs', 'dist/validators.cjs',
  'package-lock.json', 'audit-validation.mjs', '../../../contracts/fixtures/v3/blackout-output.json']) {
  const bytes = readFileSync(new URL(path, import.meta.url));
  result.sha256[path] = createHash('sha256').update(bytes).digest('hex');
  if (path === 'dist/validators.cjs') result.generated_bytes = bytes.length;
}
const common = `
  const assert = (await import('node:assert/strict')).default;
  const {readFileSync} = await import('node:fs');
  const result = JSON.parse(readFileSync('../../../contracts/fixtures/v3/blackout-output.json')).results[0];
  const scene = {api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};
  const health = {api_version:'1',kind:'health',sequence:2,session:scene.session,reason:'source_lost',scene_state:'UNKNOWN',retryable:true};
  const session = {session:scene.session,source_profile:'bench'};
  const fixtures = {scene, health, session};
  const invalid = {...scene, extra:true};
  const rssBefore = process.memoryUsage().rss;
  const start = performance.now();
`;
const variants = {
  runtime: `
    const {Ajv2020} = await import('ajv/dist/2020.js');
    const schema = JSON.parse(readFileSync('./src/scene.schema.json'));
    const ajv = new Ajv2020({strict:true});
    const validators = {
      scene: ajv.compile(schema),
      health: ajv.compile({...schema,$ref:'#/$defs/HealthEvent'}),
      session: ajv.compile({...schema,$ref:'#/$defs/SessionHandle'}),
    };
  `,
  standalone: `
    const {default: generated} = await import('./dist/validators.cjs');
    const validators = {scene:generated.validateScene,health:generated.validateHealth,session:generated.validateSession};
  `,
};
for (let round = 0; round < result.rounds; round++) {
  for (const mode of round % 2 ? ['standalone', 'runtime'] : ['runtime', 'standalone']) {
    const script = common + variants[mode] + `
      const ready_ms = performance.now()-start;
      const rss_delta_bytes = process.memoryUsage().rss-rssBefore;
      const checks = {};
      for (const [name, validate] of Object.entries(validators)) {
        const good = fixtures[name], bad = {...good, extra:true};
        const before = structuredClone([good,bad]);
        assert.equal(validate(good),true);
        assert.equal(validate(bad),false);
        assert.deepEqual([good,bad],before);
        checks[name] = {accepted:1,rejected:1};
      }
      const warm = performance.now();
      let accepted = 0;
      for(let i=0;i<${result.warm_iterations};i++) accepted += Number(validators.scene(i%2 ? invalid : scene));
      assert.equal(accepted,${result.warm_iterations / 2});
      console.log(JSON.stringify({checks,measurement:${checkOnly ? 'null' : '{ready_ms,rss_delta_bytes,warm_ms:performance.now()-warm,accepted}'}}));
    `;
    const child = spawnSync(process.execPath, ['--input-type=module', '-e', script],
      {cwd: new URL('.', import.meta.url), encoding: 'utf8', timeout: 15000});
    assert.equal(child.error, undefined);
    assert.equal(child.status, 0, `probe failed: ${mode}`);
    const report = JSON.parse(child.stdout);
    result.checks.push({round, mode, validators: report.checks});
    if (!checkOnly) result.measurements.push({round, mode, ...report.measurement});
  }
}
console.log(JSON.stringify(result, null, 2));
