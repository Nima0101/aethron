import assert from 'node:assert/strict';
import {test} from 'node:test';
import {cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const source = fileURLToPath(new URL('.', import.meta.url));
assert.ok(process.env.npm_execpath, 'run through npm run test:build');
function fixture() {
  const parent = fileURLToPath(new URL('../../../build/p33-sdk-linux/', import.meta.url));
  mkdirSync(parent, {recursive: true});
  const root = mkdtempSync(join(parent, 'build-failure-'));
  const client = join(root, 'examples/clients/typescript');
  mkdirSync(client, {recursive: true});
  for (const name of ['package.json', 'tsconfig.json', 'generate-contract.mjs', 'generate-validators.mjs', 'build.mjs']) {
    if (existsSync(join(source, name))) cpSync(join(source, name), join(client, name));
  }
  cpSync(join(source, 'src'), join(client, 'src'), {recursive: true});
  symlinkSync(join(source, 'node_modules'), join(client, 'node_modules'), 'junction');
  mkdirSync(join(root, 'contracts/openapi'), {recursive: true});
  cpSync(new URL('../../../contracts/openapi/aethron-edge-v1.json', import.meta.url), join(root, 'contracts/openapi/aethron-edge-v1.json'));
  mkdirSync(join(client, 'dist'));
  writeFileSync(join(client, 'dist/stale.js'), 'stale');
  return {root, client};
}
const build = client => spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'build'], {
  cwd: client, encoding: 'utf8', timeout: 120000, maxBuffer: 1024 * 1024,
  env: {...process.env, NPM_CONFIG_OFFLINE: 'true'},
});
for (const failure of ['contract drift', 'compiler error']) {
  test(`failed ${failure} removes stale and partial distribution`, () => {
    const {root, client} = fixture();
    try {
      const bad = failure === 'contract drift' ? join(client, 'src/types.ts') : join(client, 'src/build-probe.ts');
      const original = failure === 'contract drift' ? readFileSync(bad) : null;
      if (original) writeFileSync(bad, Buffer.concat([original, Buffer.from('\n')]));
      else writeFileSync(bad, 'export const broken: number = "not-a-number";\n');
      const result = build(client);
      assert.equal(result.error, undefined);
      assert.notEqual(result.status, 0);
      assert.match(result.stderr + result.stdout, failure === 'contract drift' ? /generated_contract_drift/ : /TS2322/);
      assert.equal(existsSync(join(client, 'dist')), false, 'failed build must withdraw its distribution');
      if (original) writeFileSync(bad, original); else rmSync(bad);
      const recovery = build(client);
      assert.equal(recovery.error, undefined);
      assert.equal(recovery.status, 0, recovery.stderr);
      const expected = readdirSync(join(source, 'dist')).sort();
      assert.deepEqual(readdirSync(join(client, 'dist')).sort(), expected);
      for (const name of expected) assert.deepEqual(readFileSync(join(client, 'dist', name)), readFileSync(join(source, 'dist', name)), name);
    } finally { rmSync(root, {recursive: true, force: true}); }
  });
}

test('direct validator generation withdraws stale output when parsing fails', () => {
  const {root, client} = fixture();
  try {
    writeFileSync(join(client, 'dist/validators.cjs'), 'stale');
    writeFileSync(join(client, 'src/scene.schema.json'), '{');
    const result = spawnSync(process.execPath, ['generate-validators.mjs'], {cwd: client, encoding: 'utf8', timeout: 30000});
    assert.equal(result.error, undefined);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(join(client, 'dist/validators.cjs')), false);
    assert.equal(readFileSync(join(client, 'dist/stale.js'), 'utf8'), 'stale', 'direct generator owns only its output');
  } finally { rmSync(root, {recursive: true, force: true}); }
});
