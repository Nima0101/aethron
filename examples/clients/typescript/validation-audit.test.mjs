import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync, mkdirSync, mkdtempSync, writeFileSync, symlinkSync, rmSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {test} from 'node:test';

test('validation probe checks all shipped validators without reporting benchmark samples', () => {
  const child = spawnSync(process.execPath, ['audit-validation.mjs', '--check'], {
    cwd: new URL('.', import.meta.url), encoding: 'utf8', timeout: 30000,
  });
  assert.equal(child.error, undefined);
  assert.equal(child.status, 0, 'controlled validation probe must succeed');
  const report = JSON.parse(child.stdout);
  assert.equal(report.mode, 'correctness-only');
  assert.equal(report.rounds, 1);
  assert.equal(report.warm_iterations, 0);
  assert.deepEqual(report.measurements, []);
  assert.deepEqual(report.checks.map(value => value.mode), ['runtime', 'standalone']);
  for (const value of report.checks) {
    assert.deepEqual(value.validators, {
      scene: {accepted: 1, rejected: 1},
      health: {accepted: 1, rejected: 1},
      session: {accepted: 1, rejected: 1},
    });
  }
  for (const file of ['audit-validation.mjs', '../../../contracts/fixtures/v3/blackout-output.json']) {
    assert.equal(report.sha256[file], createHash('sha256').update(readFileSync(new URL(file, import.meta.url))).digest('hex'));
  }
});


test('probe rejects a generated session validator that admits an extra field', () => {
  const base = new URL('../../../build/p33-sdk-linux/', import.meta.url);
  mkdirSync(base, {recursive:true});
  const root = mkdtempSync(fileURLToPath(new URL('validation-probe-', base)));
  try {
    const directory = join(root, 'examples/clients/typescript');
    mkdirSync(join(directory, 'src'), {recursive:true});
    mkdirSync(join(directory, 'dist'));
    mkdirSync(join(root, 'contracts/fixtures/v3'), {recursive:true});
    for (const file of ['audit-validation.mjs', 'generate-validators.mjs', 'package-lock.json',
      'src/scene.schema.json', 'dist/validators.cjs', '../../../contracts/fixtures/v3/blackout-output.json']) {
      writeFileSync(join(directory, file), readFileSync(new URL(file, import.meta.url)));
    }
    symlinkSync(fileURLToPath(new URL('node_modules', import.meta.url)), join(directory, 'node_modules'), 'dir');
    writeFileSync(join(directory, 'dist/validators.cjs'), '\nexports.validateSession = () => true;\n', {flag:'a'});
    const child = spawnSync(process.execPath, ['audit-validation.mjs', '--check'], {
      cwd:directory, encoding:'utf8', timeout:30000,
    });
    assert.equal(child.error, undefined);
    assert.notEqual(child.status, 0);
    assert.match(child.stderr, /probe failed: standalone/);
    assert.equal(child.stdout, '', 'no success report may escape a failed comparison');
  } finally { rmSync(root, {recursive:true,force:true}); }
});
