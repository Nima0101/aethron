// Audit prototype only: token admission, not a qualification validator.
// Reads the same trusted synthetic vectors used by the production contract test.
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const vectorBytes = readFileSync(new URL('./ingress-vectors-v1.json', import.meta.url));
const vectors = JSON.parse(vectorBytes);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
let sourceAvailable = false;
JSON.parse('1', (key, value, context) => {
  sourceAvailable = context?.source === '1';
  return value;
});
if (!sourceAvailable) throw new Error('source-aware reviver unavailable');

function admitted(hex) {
  const bytes = Buffer.from(hex, 'hex');
  if (bytes.length > 65536) return false;
  try {
    // ignoreBOM=true retains the BOM so JSON.parse can reject it.
    const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
    JSON.parse(text, (key, value, context) => {
      if (typeof value === 'number') {
        const token = context.source;
        if (!/^-?(0|[1-9][0-9]*)$/.test(token) || token.length > 17 ||
            !Number.isSafeInteger(value) || Math.abs(value) > 2 ** 53 - 1000) {
          throw new Error('invalid_numeric_token');
        }
      }
      return value;
    });
    return true;
  } catch {
    return false;
  }
}

const cases = vectors.map(vector => {
  const accepted = admitted(vector.hex);
  return { id: vector.id, accepted, expected_accepted: !vector.reject,
    matches: accepted === !vector.reject };
});
console.log(JSON.stringify({
  audit_policy_version: 3,
  scope: 'ingress_token_probe_only_no_schema_or_semantic_validation',
  runtime: process.version,
  source_aware_reviver: sourceAvailable,
  cases,
  parity: cases.every(item => item.matches),
  source_sha256: {
    'qualification/technology/ingress-probe.mjs': digest(readFileSync(new URL(import.meta.url))),
    'qualification/technology/ingress-vectors-v1.json': digest(vectorBytes),
  },
  physical_qualification_passed: false,
}, null, 2));
