// Bounded audit probe only: crypto primitives are NOT passport admission.
import assert from 'node:assert/strict';
import { createHash, createPublicKey, verify } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';

const raw = readFileSync(0);
assert(raw.length <= 65536);
const inputs = JSON.parse(raw.toString('utf8'));
assert(inputs.length === 6);
const results = inputs.map(({ publicKey, signature, message }) => {
  const key = createPublicKey({
    key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), Buffer.from(publicKey, 'hex')]),
    format: 'der', type: 'spki',
  });
  return verify(null, Buffer.from(message, 'hex'), key, Buffer.from(signature, 'hex'));
});
// Show parser semantics that a production candidate must explicitly repair.
assert.equal(JSON.parse('{"version":0,"version":1}').version, 1);
assert.equal(JSON.parse('1.0'), JSON.parse('1e0'));
const blob = Buffer.alloc(65536, 0x61);
const started = performance.now();
let digest;
for (let i = 0; i < 16; i++) digest = createHash('sha256').update(blob).digest('hex');
process.stdout.write(JSON.stringify({
  node: process.version, crypto_accepts: results, hash_digest: digest,
  hash_1mib_ms: performance.now() - started,
  duplicate_keys_collapsed: true, float_lexemes_collapsed: true,
}));
