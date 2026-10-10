# Passport schema conformance v1

The payload, signature envelope, externally provisioned trust policy, offline task
description and direct federation snapshot need portable
structural schemas for publishers and SDK consumers. These are tooling contracts, not
an alternate verifier. Frozen safety rules and passport v1 timing/resource bounds remain
unchanged. No schema success can grant authority, authenticate a statement or qualify data.

## Technology decision

Requirements: language-neutral closed objects, bounded arrays/strings, safe integer
ranges, no remote schema resolution and no production dependency or platform SDK changes.
Use [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) rather than a language's
classes or handwritten copies of structural checks. Its integer model is mathematical:
it cannot distinguish the JSON lexical encodings `1` and `1.0` after decoding.
Cross-field key hashes, time intervals, signatures, revocation, canonical bytes and
complete evidence references therefore remain the normative runtime verifier's job.

[python-jsonschema](https://python-jsonschema.readthedocs.io/en/stable/validate/) and
[Ajv](https://ajv.js.org/json-schema.html) both support this draft. Choose the maintained
python-jsonschema 4.26.0 validator for a separate Python 3.13 hosted conformance job:
installed metaschemas and an explicit no-retrieval registry support offline checks,
and tests distinguish structural acceptance from actual runtime authentication.
The [V3 review](../../engineering/reviews/p16-conformance-v3.md) compares Ajv, CUE
and native validation alternatives. This is a test-tool choice, not a language requirement for
consumers or a second implementation of another lane's SDK. No runtime dependency changes.

## Conformance boundary

Each schema is self-contained; references, if present, stay inside the same document.
Closed objects reject unknown and missing fields. Identifier patterns must reject trailing
line terminators as well as ordinary invalid characters, using an ECMAScript-compatible
absolute-end assertion. Plain `$` permits a final newline in common regex engines and is
insufficient for this profile's identifiers. Correcting that pattern aligns tooling with
the existing `fullmatch` runtime contract; it does not change accepted runtime input.

The envelope fixes the payload type and exactly one signature. Base64 patterns assert
padding and zero unused bits rather than relying on the optional `contentEncoding`
annotation. Policy schemas fix key/revocation list limits and scalar types, but do not
authenticate provisioning or validate key-ID hashes. Array uniqueness in schemas cannot
substitute for the runtime's uniqueness by capability name, digest and key ID.

Tests cover the passport and evidence-binding portable envelope/policy fixtures,
missing/unknown properties, scalar confusion,
resource bounds, invalid base64, trailing newlines, and intentionally well-shaped yet
expired/revoked/forged statements that the runtime must still reject. External `$ref`
retrieval is forbidden by the test registry. The normal dependency-free runtime test
suite may skip the optional schema tool. Install `requirements-passport-conformance.txt`
to run these comparisons; it includes the pinned passport crypto closure. The workflow
configures a job that explicitly imports both schema and crypto backends before running;
this describes configuration, not an observed hosted success. See the
[verification evidence boundary](verification-evidence-v1.md). The runtime
comparison must authenticate a known-good fixture and reject negative fixtures for
their expected reasons; an unavailable or always-rejecting backend cannot pass it.

The [current claim-vocabulary review](../../engineering/reviews/p16-schema-claims-current-v3.md)
adds paired schema/runtime checks for all 27 single-reference capability/kind/outcome
combinations and 12 unsupported or type-confused claims. These are structural and
canonicalization controls, not authentication or qualification of those assertions.
Five independently removed payload constraints previously survived the passport-schema
tests; each is now detected. Published schemas and runtime behavior remain unchanged.

## Task and federation coverage

The [task schema](../../../contracts/interop/task-v1.schema.json) enforces the two
verification-only kinds and their distinct evidence-list and byte-budget constraints.
The [federation schema](../../../contracts/interop/federation-v1.schema.json) enforces
closed rows, scalar ranges, issuer/capability lists and the 16-peer limit. Both schemas
are self-contained and use the same safe-integer and absolute-end identifier profile.

The normative [task](task-v1.md) and [federation](federation-v1.md) runtime contracts
still enforce lexical/byte/depth limits, canonical identity, interval relationships,
pins, freshness, revision floors and authenticated bundle scope. Full-row uniqueness
in JSON Schema does not enforce uniqueness by remote-domain name or prevent a peer
from using the local-domain alias. Retained tests demonstrate these structural-success,
runtime-rejection cases and require genuine positive runtime results as controls.
See the [technology and coverage review](../../engineering/reviews/p16-interop-schemas-v3.md).

## Published edge UNKNOWN evidence

The [portable edge corpus](../../../examples/interop/edge-unknown-vectors-v1.json)
consumes the existing API v1 `V3Snapshot` schema and fixed v3 UNKNOWN output from
protected main `a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46`. Exact source hashes pin the
reviewed contract and fixture; producer changes require deliberate compatibility review.
No peer implementation or schema is copied or changed. The conformance job validates
the source structure with local references, then checks P16 byte binding and negatives.

The fixture has no tracks and no observation evidence. Its independently controlled
recommendation remains data; the test never invokes a controller. Signed `unknown`
outcomes remain unknown. P16 UTC expiry concerns the verification descriptions, while
scene monotonic milliseconds remain uninterpreted evidence bytes. A bound result does
not translate clocks, establish live freshness or qualify sensor observations.
This is one offline producer-contract/consumer check, not P2/P3/P14 runtime integration.
See [review and technology decision](../../engineering/reviews/p16-edge-conformance-v3.md).


## P2 synthetic packet consumer

`examples/interop/sensor-packet-vectors-v1.json` binds two separate immutable blobs:
UTF-8 layout JSON and binary pixel bytes. Five portable cases cover exact input,
layout substitution, pixel modification, a newly signed truncated payload and newly
signed missing-depth samples. Each case supplies complete P16 verification inputs.

Run the optional Python 3.13 consumer using
`python -m pip install --only-binary=:all: -r requirements-passport-sensor-conformance.txt`,
then `PYTHONPATH=.:integrations/edge python -m unittest discover -s tests/interop_consumers -p test_sensor_packets.py -v`.
Imports fail if dependencies are absent; this job has no optional success-by-skip path.
The consumer calls the published P2 `decode_image` API without copying its parser.

Authentication and packet decoding are separate results. A new valid signature can
bind malformed bytes; the producer still rejects a truncated image. Zero depth remains
unknown. Layout scale is an assertion, not calibrated distance; matching bytes never
qualifies measurement truth, observation freshness or motion authority. These are
analytical fixtures with a public test signing key, not physical sensor observations.
No replay parser, recorded-clock conversion or sensor runtime is qualified here.
See the [review and evidence](../../engineering/reviews/p16-sensor-conformance-v3.md).
