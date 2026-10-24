import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawnSync} from 'node:child_process';
import {cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Ajv2020} from '../clients/typescript/node_modules/ajv/dist/2020.js';

const source = fileURLToPath(new URL('.', import.meta.url));
assert.ok(process.env.npm_execpath, 'run through npm run test:build');

test('operator build decision rejects undocumented architecture claims', () => {
  const read = name => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
  const validate = new Ajv2020({strict: true}).compile(read('./build-adr.schema.json'));
  const adr = read('./build-adr.json');
  assert.equal(validate(adr), true, JSON.stringify(validate.errors));
  assert.equal(validate({...adr, qualified: true}), false);
  assert.equal(validate({...adr, c4: {...adr.c4, unreviewed: 'claim'}}), false);
  assert.equal(validate({...adr, alternatives: [{...adr.alternatives[0], measured: true}, ...adr.alternatives.slice(1)]}), false);
});

test('failed operator compilation withdraws distribution and a corrected build recovers', () => {
  const parent = fileURLToPath(new URL('../../build/p33-sdk-linux/', import.meta.url));
  mkdirSync(parent, {recursive: true});
  const root = mkdtempSync(join(parent, 'operator-build-'));
  const client = join(root, 'examples/operator');
  try {
    mkdirSync(join(client, 'src'), {recursive: true});
    for (const name of ['package.json', 'tsconfig.json', 'build.mjs']) {
      if (existsSync(join(source, name))) cpSync(join(source, name), join(client, name));
    }
    const sibling = join(root, 'examples/clients/typescript');
    mkdirSync(sibling, {recursive: true});
    symlinkSync(fileURLToPath(new URL('../clients/typescript/node_modules', import.meta.url)), join(sibling, 'node_modules'), 'junction');
    mkdirSync(join(client, 'dist'));
    writeFileSync(join(client, 'dist/stale.js'), 'stale');
    writeFileSync(join(client, 'unrelated.txt'), 'preserve');
    writeFileSync(join(client, 'src/probe.ts'), 'export const state: string = "UNKNOWN";\n');
    writeFileSync(join(client, 'src/broken.ts'), 'export const broken: number = "bad";\n');
    const build = () => spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'build'], {
      cwd: client, encoding: 'utf8', timeout: 60000, maxBuffer: 1024 * 1024,
      env: {...process.env, NPM_CONFIG_OFFLINE: 'true'},
    });
    const failed = build();
    assert.equal(failed.error, undefined);
    assert.notEqual(failed.status, 0);
    assert.match(failed.stdout + failed.stderr, /TS2322/);
    assert.equal(existsSync(join(client, 'dist')), false, 'a failed build must withdraw stale and partial output');
    assert.equal(readFileSync(join(client, 'unrelated.txt'), 'utf8'), 'preserve');
    rmSync(join(client, 'src/broken.ts'));
    const recovered = build();
    assert.equal(recovered.error, undefined);
    assert.equal(recovered.status, 0, recovered.stdout + recovered.stderr);
    assert.deepEqual(readdirSync(join(client, 'dist')).sort(), ['probe.d.ts', 'probe.js']);
    assert.equal(readFileSync(join(client, 'dist/probe.js'), 'utf8'), 'export const state = "UNKNOWN";\n');
    assert.equal(readFileSync(join(client, 'dist/probe.d.ts'), 'utf8'), 'export declare const state: string;\n');
  } finally { rmSync(root, {recursive: true, force: true}); }
});

test('compiler failure after a partial write withdraws the new output', () => {
  const parent = fileURLToPath(new URL('../../build/p33-sdk-linux/', import.meta.url));
  mkdirSync(parent, {recursive: true});
  const root = mkdtempSync(join(parent, 'operator-partial-'));
  const client = join(root, 'examples/operator');
  const compiler = join(root, 'examples/clients/typescript/node_modules/typescript/bin');
  try {
    mkdirSync(client, {recursive: true});
    mkdirSync(compiler, {recursive: true});
    for (const name of ['package.json', 'build.mjs']) cpSync(join(source, name), join(client, name));
    writeFileSync(join(compiler, 'tsc'), `
      const fs = require('node:fs');
      fs.mkdirSync('dist'); fs.writeFileSync('dist/partial.js', 'partial');
      process.stderr.write('controlled_partial_write_failure'); process.exit(7);
    `);
    const result = spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'build'], {
      cwd: client, encoding: 'utf8', timeout: 15000, maxBuffer: 1024 * 1024,
      env: {...process.env, NPM_CONFIG_OFFLINE: 'true'},
    });
    assert.equal(result.error, undefined);
    assert.notEqual(result.status, 0);
    assert.match(result.stdout + result.stderr, /controlled_partial_write_failure/);
    assert.match(result.stderr, /operator_build_failed/);
    assert.equal(existsSync(join(client, 'dist')), false);
  } finally { rmSync(root, {recursive: true, force: true}); }
});
