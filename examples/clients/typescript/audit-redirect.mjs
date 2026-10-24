import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';

// Each authenticated phase must independently prevent redirect destination I/O.
// Only copied modules are mutated; all requests use synthetic loopback fixtures.
const source = readFileSync(new URL('./dist/client.js', import.meta.url), 'utf8');
const tests = readFileSync(new URL('./redirect.test.mjs', import.meta.url), 'utf8');
const policy = "redirect: 'error'";
assert.equal(source.split(policy).length, 4, 'exactly three request policies required');
assert.equal(tests.split("'./dist/client.js'").length, 2);
const directory = mkdtempSync(join(tmpdir(), 'aethron-redirect-audit-'));
try {
  for (const [index, phase] of ['POST', 'GET', 'DELETE'].entries()) {
    let occurrence = 0;
    let mutated = source.replaceAll(policy, () => occurrence++ === index ? "redirect: 'follow'" : policy);
    for (const file of ['validators.cjs', 'wire.js', 'session.js']) {
      mutated = mutated.replace(`'./${file}'`, JSON.stringify(new URL(`./dist/${file}`, import.meta.url).href));
    }
    const url = 'data:text/javascript;base64,' + Buffer.from(mutated).toString('base64');
    const path = join(directory, `${phase}.test.mjs`);
    writeFileSync(path, tests.replace("'./dist/client.js'", JSON.stringify(url)));
    const result = spawnSync(process.execPath, ['--test', path], {
      encoding: 'utf8', timeout: 15000, maxBuffer: 1024 * 1024, shell: false,
    });
    console.log(JSON.stringify({phase, status: result.status, error: result.error?.code,
      tests: result.stdout?.match(/# tests (\d+)/)?.[1], failures: result.stdout?.match(/# fail (\d+)/)?.[1]}));
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    assert.match(result.stdout, /# tests 31\n/);
    assert.match(result.stdout, /# pass 21\n/);
    assert.match(result.stdout, /# fail 10\n/);
    assert.match(result.stdout, /# cancelled 0\n/);
    assert.match(result.stdout, /# skipped 0\n/);
    assert.equal((result.stdout.match(new RegExp(`^not ok \\d+ - ${phase} `, 'gm')) ?? []).length, 10);
    assert.equal((result.stdout.match(/error: \|-\n    redirect destination must receive no request/g) ?? []).length, 10);
    assert.doesNotMatch(result.stdout + result.stderr, /ERR_MODULE_NOT_FOUND|SyntaxError/);
  }
} finally { rmSync(directory, {recursive: true, force: true}); }
