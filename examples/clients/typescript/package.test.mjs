import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {test} from 'node:test';

const root = fileURLToPath(new URL('./', import.meta.url));
const dist = join(root, 'dist');
const expected = ['LICENSE', 'README.md', 'package.json',
  'dist/client.js', 'dist/client.d.ts', 'dist/session.js', 'dist/session.d.ts',
  'dist/wire.js', 'dist/wire.d.ts', 'dist/types.js', 'dist/types.d.ts',
  'dist/validators.cjs', 'dist/scene.schema.json'].sort();

test('packed client excludes stale modules and diagnostic files', () => {
  // Do not build here: packing must reject extra files even in a dirty build directory.
  const probe = mkdtempSync(join(dist, 'pack-probe-'));
  let packed;
  try {
    writeFileSync(join(probe, 'stale.js'), 'export const synthetic = true;\n');
    writeFileSync(join(probe, 'diagnostic.json'), '{"synthetic_private_marker":true}\n');
    mkdirSync(join(probe, 'cache'));
    writeFileSync(join(probe, 'cache', 'sample.bin'), 'synthetic');
    const npm = process.env.npm_execpath;
    assert.ok(npm, 'Run through npm run test:package so the invoking npm CLI is explicit');
    packed = JSON.parse(execFileSync(process.execPath, [npm, 'pack', '--dry-run', '--json',
      '--ignore-scripts', '--offline', '--cache', join(probe, 'npm-cache')],
    {cwd: root, encoding: 'utf8', timeout: 20000, maxBuffer: 1024 * 1024}));
  } finally {
    rmSync(probe, {recursive: true, force: true});
  }
  assert.equal(packed.length, 1);
  assert.deepEqual(packed[0].files.map(file => file.path).sort(), expected);
});

test('package contains the unchanged repository license text', () => {
  const path = new URL('./LICENSE', import.meta.url);
  let license;
  try { license = readFileSync(path); } catch { /* Assertion reports absent package input. */ }
  assert.ok(license, 'package LICENSE must exist');
  assert.deepEqual(license, readFileSync(new URL('../../../LICENSE', import.meta.url)));
});
