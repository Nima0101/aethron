import {rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const directory = fileURLToPath(new URL('.', import.meta.url));
const output = new URL('./dist/', import.meta.url);

try {
  rmSync(output, {recursive: true, force: true});
  const result = spawnSync(process.execPath, [
    '../clients/typescript/node_modules/typescript/bin/tsc', '-p', 'tsconfig.json',
  ], {
    cwd: directory, stdio: 'inherit', timeout: 30000, killSignal: 'SIGKILL', shell: false,
  });
  if (result.error) throw new Error('operator_build_failed', {cause: result.error});
  if (result.status !== 0) throw new Error(`operator_build_failed: exit=${result.status} signal=${result.signal}`);
} catch (error) {
  rmSync(output, {recursive: true, force: true});
  throw error;
}
