import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';

// The watchdog must clean up a broken client without making its test pass.
// Mutations run from copied modules; production source/dist stay untouched.
const source = readFileSync(new URL('./dist/client.js', import.meta.url), 'utf8');
const tests = readFileSync(new URL('./errors.test.mjs', import.meta.url), 'utf8');
const directory = mkdtempSync(join(tmpdir(), 'aethron-cancel-audit-'));
try {
  for (const [phase, before, after] of [
    ['POST', "contract: 'warn' }), signal", "contract: 'warn' }), signal: undefined"],
    ['GET', 'headers, signal: eventSignal, redirect:', 'headers, signal: undefined, redirect:'],
  ]) {
    assert.equal(source.split(before).length, 2, 'mutation must match exactly once');
    let mutated = source.replace(before, after);
    for (const file of ['validators.cjs', 'wire.js', 'session.js']) {
      mutated = mutated.replace(`'./${file}'`, JSON.stringify(new URL(`./dist/${file}`, import.meta.url).href));
    }
    const url = 'data:text/javascript;base64,' + Buffer.from(mutated).toString('base64');
    assert.equal(tests.split("'./dist/client.js'").length, 2);
    const path = join(directory, `${phase}.test.mjs`);
    writeFileSync(path, tests.replace("'./dist/client.js'", JSON.stringify(url)));
    const result = spawnSync(process.execPath, ['--test',
      `--test-name-pattern=^native caller cancellation during ${phase} headers keeps private reasons local$`, path], {
      encoding: 'utf8', timeout: 15000, maxBuffer: 1024 * 1024, shell: false,
    });
    const summary = {phase, status: result.status, error: result.error?.code,
      tests: result.stdout?.match(/# tests (\d+)/)?.[1],
      failures: result.stdout?.match(/# fail (\d+)/)?.[1],
      watchdogAssertion: result.stdout?.includes('watchdog must not substitute for client cancellation')};
    console.log(JSON.stringify(summary));
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1, `${phase} lost cancellation must fail independently of watchdog cleanup`);
    assert.match(result.stdout, /# tests 1\n/);
    assert.match(result.stdout, /# fail 1\n/);
    assert.match(result.stdout, /# cancelled 0\n/);
    assert.match(result.stdout, /watchdog must not substitute for client cancellation/);
    assert.doesNotMatch(result.stdout + result.stderr, /ERR_MODULE_NOT_FOUND|SyntaxError/);
  }
} finally { rmSync(directory, {recursive: true, force: true}); }
