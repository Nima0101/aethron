// Audit primitive only; this does not implement artifact admission or reports.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const sourceUrl = new URL(import.meta.url);
const sourceDigest = digest(readFileSync(sourceUrl));
const inputs = Array.from({ length: 4 }, (_, value) => Buffer.alloc(1048576, value));
const samples = [];
let hashes;
for (let iteration = 0; iteration < 10; iteration++) {
  const start = process.hrtime.bigint();
  // Buffer is mutable: take owned copies before the binding calculation.
  const owned = inputs.map(value => Buffer.from(value));
  hashes = owned.map(digest);
  samples.push(Number(process.hrtime.bigint() - start));
}
const mutable = Buffer.from('abc');
const alias = mutable.subarray();
const owned = Buffer.from(mutable);
mutable[0] = 0;
if (digest(readFileSync(sourceUrl)) !== sourceDigest) {
  throw new Error('probe_sources_changed');
}
console.log(JSON.stringify({
  audit_policy_version: 3,
  scope: 'native_sha256_and_ownership_probe_only',
  runtime: process.version,
  known_vectors: [digest(Buffer.alloc(0)), digest(Buffer.from('abc'))],
  four_mib_digests: hashes,
  copy_and_hash_elapsed_ns: samples,
  alias_changed: digest(alias) !== digest(owned),
  owned_preserved: digest(owned) === digest(Buffer.from('abc')),
  physical_qualification_passed: false,
  source_observation: 'equal_before_and_after_workload',
  source_sha256: {
    'qualification/technology/hash-probe.mjs': sourceDigest,
  },
}, null, 2));
