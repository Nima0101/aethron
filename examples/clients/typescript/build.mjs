import {rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

// One build at a time per package directory. dist is entirely generated.
const directory = fileURLToPath(new URL('.', import.meta.url));
const output = new URL('./dist/', import.meta.url);
try {
  rmSync(output, {recursive: true, force: true});
  for (const args of [
    ['generate-contract.mjs', '--check'],
    ['generate-validators.mjs'],
    ['node_modules/typescript/bin/tsc', '-p', 'tsconfig.json'],
  ]) {
    const result = spawnSync(process.execPath, args, {
      cwd: directory, stdio: 'inherit', timeout: 30000, killSignal: 'SIGKILL', shell: false,
    });
    if (result.error || result.status !== 0) throw new Error('client_build_failed');
  }
} catch (error) {
  rmSync(output, {recursive: true, force: true});
  throw error;
}
