import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
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

test('installed public declarations and offline uninstall/reinstall preserve the client boundary', () => {
  const npm = process.env.npm_execpath;
  assert.ok(npm, 'Run through npm run test:package');
  const work = mkdtempSync(join(tmpdir(), 'aethron-client-types-'));
  const options = {encoding: 'utf8', timeout: 30000, maxBuffer: 1024 * 1024};
  try {
    const packed = JSON.parse(execFileSync(process.execPath, [npm, 'pack', '--json',
      '--ignore-scripts', '--offline', '--pack-destination', work], {...options, cwd: root}));
    assert.equal(packed.length, 1);
    writeFileSync(join(work, 'package.json'), JSON.stringify({private: true, type: 'module'}));
    execFileSync(process.execPath, [npm, 'install', '--offline', '--ignore-scripts',
      '--no-audit', '--no-fund', join(work, packed[0].filename)], {...options, cwd: work});
    copyFileSync(new URL('./public-types.test.ts', import.meta.url), join(work, 'consumer.ts'));
    // The fixture imports only the package entry point from outside this checkout.
    try {
      execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'),
        '--strict', '--noEmit', '--target', 'es2022', '--module', 'nodenext',
        '--moduleResolution', 'nodenext', 'consumer.ts'], {...options, cwd: work});
    } catch (error) {
      assert.fail(error.stdout || error.message);
    }
    copyFileSync(new URL('./installed-runtime.mjs', import.meta.url), join(work, 'consumer.mjs'));
    copyFileSync(new URL('../../../contracts/fixtures/v3/blackout-output.json', import.meta.url),
      join(work, 'fixture.json'));
    const runConsumer = () => JSON.parse(execFileSync(process.execPath,
      ['--disallow-code-generation-from-strings', 'consumer.mjs'], {...options, cwd: work}));
    assert.deepEqual(runConsumer(), {checks: 11, current_state: 'UNKNOWN'});
    execFileSync(process.execPath, [npm, 'uninstall', '--offline', '--ignore-scripts',
      '--no-audit', '--no-fund', '--save', 'aethron-edge-client-example'], {...options, cwd: work});
    assert.equal(existsSync(join(work, 'node_modules/aethron-edge-client-example')), false);
    const manifest = JSON.parse(readFileSync(join(work, 'package.json'), 'utf8'));
    const lock = JSON.parse(readFileSync(join(work, 'package-lock.json'), 'utf8'));
    assert.equal(manifest.dependencies?.['aethron-edge-client-example'], undefined);
    assert.equal(lock.packages['node_modules/aethron-edge-client-example'], undefined);
    execFileSync(process.execPath, ['--input-type=module', '-e',
      "import assert from 'node:assert/strict'; await assert.rejects(import('aethron-edge-client-example'), {code:'ERR_MODULE_NOT_FOUND'});"],
    {...options, cwd: work});
    execFileSync(process.execPath, [npm, 'install', '--offline', '--ignore-scripts',
      '--no-audit', '--no-fund', join(work, packed[0].filename)], {...options, cwd: work});
    assert.deepEqual(runConsumer(), {checks: 11, current_state: 'UNKNOWN'});
  } finally {
    rmSync(work, {recursive: true, force: true});
  }
});
