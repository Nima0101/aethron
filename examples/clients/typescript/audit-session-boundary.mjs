import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';

// Mutate a copied, built module only. Original source and dist remain untouched.
const source = readFileSync(new URL('./dist/session.js', import.meta.url), 'utf8');
const test = readFileSync(new URL('./session-boundary.test.mjs', import.meta.url), 'utf8');
const directory = mkdtempSync(join(tmpdir(), 'aethron-session-audit-'));
try {
  for (const [name, before, after, failures] of [
    ['nonfatal-utf8', 'fatal: true', 'fatal: false', 5],
    ['increased-byte-limit', 'MAX_SESSION_BYTES = 65536', 'MAX_SESSION_BYTES = 65537', 1],
  ]) {
    assert.equal(source.split(before).length, 2, 'mutation must match exactly once');
    const mutated = source.replace(before, after)
      .replace("'./validators.cjs'", JSON.stringify(new URL('./dist/validators.cjs', import.meta.url).href))
      .replace("'./wire.js'", JSON.stringify(new URL('./dist/wire.js', import.meta.url).href));
    const url = 'data:text/javascript;base64,' + Buffer.from(mutated).toString('base64');
    const path = join(directory, `${name}.test.mjs`);
    assert.equal(test.split("'./dist/session.js'").length, 2);
    writeFileSync(path, test.replace("'./dist/session.js'", JSON.stringify(url)));
    const result = spawnSync(process.execPath, ['--test', path], {
      encoding: 'utf8', timeout: 10000, maxBuffer: 1024 * 1024, shell: false,
    });
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    assert.match(result.stdout, new RegExp(`# fail ${failures}\\n`));
    assert.match(result.stdout, /# tests 9\n/);
    assert.match(result.stdout, /# cancelled 0\n/);
    assert.match(result.stdout, /# skipped 0\n/);
    assert.doesNotMatch(result.stdout + result.stderr, /ERR_MODULE_NOT_FOUND|SyntaxError/);
    console.log(JSON.stringify({mutation: name, tests: 9, expected_failures: failures, rejected: true}));
  }
} finally { rmSync(directory, {recursive: true, force: true}); }
