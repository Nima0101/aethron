# Offline passport fixtures

These statements describe synthetic software artifacts. The published RFC 8032 test
key is deliberately public and must never be provisioned as a deployment trust root.
Timestamps are artificial; passing `now_s=1500` is appropriate only for these fixtures.

Install the optional verifier with `python -m pip install -c requirements-passports.txt
'.[passports]'` from the repository root. Run
`python -m unittest discover -s tests -p 'test_passport*.py' -v`.

[The portable vectors](vectors.json) contain the exact canonical payload, SHA-256,
DSSE signing bytes (hex), envelopes, externally supplied policies, caller arguments and
expected fixed results. They retain failed recorded evidence and rejection cases for
expiry, revoked evidence, policy rollback, forged signatures and signed authority
escalation. [The structural JSON schema](../../contracts/interop/passport-v1.schema.json)
and [normative profile](../../docs/architecture/interop/passport-v1.md) define the format.
Companion schemas cover the [signature envelope](../../contracts/interop/passport-envelope-v1.schema.json)
and [provisioned trust policy](../../contracts/interop/passport-policy-v1.schema.json).
They check structure only; full signature, interval, revocation and canonical-wire checks
remain mandatory. [Schema conformance](../../docs/architecture/interop/schema-conformance-v1.md)
includes a test-only Python 3.13 toolchain: install `requirements-passport-conformance.txt`
and run `python -m unittest discover -s tests -p test_passport_schemas.py -v`.

```python
import json
from pathlib import Path
from aethron.passports import verify

vectors = json.loads(Path("examples/passports/vectors.json").read_bytes())
case = vectors["cases"][0]
result = verify(case["envelope"].encode(), case["policy"].encode(), **case["arguments"])
assert result.status == "authenticated"
assert result.motion_authority is False
assert result.evidence_verified is False
```

For real inputs, obtain policy through authenticated local provisioning, compute the
expected digest from the exact software artifact, and supply trusted UTC time plus
persisted time/revision floors. Never obtain these trust inputs from the passport.
Reverify at use time. The signature verifier performs no network access or evidence-content reads;
a signature authenticates the statement, including its negative evidence, not its truth.
Expired snapshots cannot establish current revocation status. No controller, physical
qualification, accreditation, or deployment authorization is provided.

## Bind local evidence content

The [bounded content adapter](../../docs/architecture/interop/evidence-binding-v1.md)
rehashes supplied immutable bytes and requires every signed evidence reference to match.
It retains failed/unknown outcomes; digest equality does not qualify the report's truth.
[Portable content vectors](evidence-vectors.json) include missing negative evidence,
substitution, duplicates, revocation, expiry and forged signatures.

```python
import json
from pathlib import Path
from aethron.passport_evidence import verify_evidence

case = json.loads(Path("examples/passports/evidence-vectors.json").read_bytes())["cases"][0]
blobs = tuple(bytes.fromhex(blob) for blob in case["evidence_hex"])
result = verify_evidence(case["envelope"].encode(), case["policy"].encode(), blobs, **case["arguments"])
assert result.status == "bound"
assert [item.outcome for item in result.evidence] == ["passed", "failed", "unknown"]
assert result.motion_authority is False
assert result.evidence_verified is False
```
