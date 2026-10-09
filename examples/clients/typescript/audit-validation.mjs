// Bounded audit probe; sequential children only. Run after npm run build.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

const result = {node: process.version, platform: process.platform, arch: process.arch,
  rounds: 3, warm_iterations: 10000, measurements: [], sha256: {}, generated_bytes: 0};
for (const path of ['src/scene.schema.json', 'generate-validators.mjs', 'dist/validators.cjs', 'package-lock.json']) {
  const bytes = readFileSync(new URL(path, import.meta.url));
  result.sha256[path] = createHash('sha256').update(bytes).digest('hex');
  if (path === 'dist/validators.cjs') result.generated_bytes = bytes.length;
}
const common = `
  const {readFileSync} = await import('node:fs');
  const result = JSON.parse(readFileSync('../../../contracts/fixtures/v3/blackout-output.json')).results[0];
  const scene = {api_version:'1',kind:'scene',sequence:1,session:'a'.repeat(32),clock:{domain:'edge_monotonic',emitted_ms:0,valid_for_ms:100},result};
  const invalid = {...scene, extra:true};
  const rssBefore = process.memoryUsage().rss;
  const start = performance.now();
`;
const variants = {
  runtime: `
    const {Ajv2020} = await import('ajv/dist/2020.js');
    const schema = JSON.parse(readFileSync('./src/scene.schema.json'));
    const ajv = new Ajv2020({strict:true});
    const validate = ajv.compile(schema);
    ajv.compile({...schema,$ref:'#/$defs/HealthEvent'});
  `,
  standalone: `const {default: validators} = await import('./dist/validators.cjs'); const validate = validators.validateScene;`,
};
for (let round = 0; round < result.rounds; round++) {
  for (const mode of round % 2 ? ['standalone', 'runtime'] : ['runtime', 'standalone']) {
    const script = common + variants[mode] + `
      const ready_ms = performance.now()-start;
      const rss_delta_bytes = process.memoryUsage().rss-rssBefore;
      const warm = performance.now();
      let accepted = 0;
      for(let i=0;i<10000;i++) accepted += Number(validate(i%2 ? invalid : scene));
      console.log(JSON.stringify({ready_ms,rss_delta_bytes,warm_ms:performance.now()-warm,accepted}));
    `;
    const child = spawnSync(process.execPath, ['--input-type=module', '-e', script],
      {cwd: new URL('.', import.meta.url), encoding: 'utf8', timeout: 15000});
    assert.equal(child.error, undefined);
    assert.equal(child.status, 0, `probe failed: ${mode}`);
    const measurement = JSON.parse(child.stdout);
    assert.equal(measurement.accepted, 5000);
    result.measurements.push({round, mode, ...measurement});
  }
}
console.log(JSON.stringify(result, null, 2));
