// Audit primitive only; this does not implement artifact admission or reports.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const sourceUrl = new URL(import.meta.url);
const sourceDigest = digest(readFileSync(sourceUrl));
const inputs = Array.from({ length: 4 }, (_, value) => Buffer.alloc(1048576, value));
// Fixed synthetic expectations, independently checked outside this runtime.
const expectedHashes = [
  '30e14955ebf1352266dc2ff8067e68104607e750abb9d3b36582b8af909fcb58',
  'ee78cd29d3a534713b36e6ff6fa3668c8a8f851a542d5eb2401c25ca4e057d02',
  '2fa4430272111c7854b204001461e16f2c73725b07dde2b6d1dc4f2aa8fe18da',
  '9ed3b916b5b6b1dbe61b8844c8130657b9bc4f7ff80a07c7835989c911ad430a',
];
const expectedKnown = [
  'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
];
function requireHashes(actual, expected) {
  if (actual.length !== expected.length ||
      actual.some((value, index) => value !== expected[index])) {
    throw new Error('hash_probe_result_failed');
  }
}
const samples = [];
let hashes;
for (let iteration = 0; iteration < 10; iteration++) {
  const start = process.hrtime.bigint();
  // Buffer is mutable: take owned copies before the binding calculation.
  const owned = inputs.map(value => Buffer.from(value));
  hashes = owned.map(digest);
  samples.push(Number(process.hrtime.bigint() - start));
  requireHashes(hashes, expectedHashes);
}
const mutable = Buffer.from('abc');
const alias = mutable.subarray();
const owned = Buffer.from(mutable);
mutable[0] = 0;
const knownVectors = [digest(Buffer.alloc(0)), digest(Buffer.from('abc'))];
requireHashes(knownVectors, expectedKnown);
const aliasChanged = digest(alias) !== digest(owned);
const ownedPreserved = digest(owned) === expectedKnown[1];
if (!aliasChanged || !ownedPreserved) throw new Error('hash_probe_result_failed');
if (digest(readFileSync(sourceUrl)) !== sourceDigest) {
  throw new Error('probe_sources_changed');
}
console.log(JSON.stringify({
  audit_policy_version: 3,
  scope: 'native_sha256_and_ownership_probe_only',
  runtime: process.version,
  known_vectors: knownVectors,
  four_mib_digests: hashes,
  copy_and_hash_elapsed_ns: samples,
  all_measured_results_checked: true,
  result_validation_excluded_from_measurements: true,
  alias_changed: aliasChanged,
  owned_preserved: ownedPreserved,
  physical_qualification_passed: false,
  source_observation: 'equal_before_and_after_workload',
  source_sha256: {
    'qualification/technology/hash-probe.mjs': sourceDigest,
  },
}, null, 2));
