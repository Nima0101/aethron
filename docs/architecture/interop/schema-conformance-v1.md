# Passport schema conformance v1

The payload, signature envelope and externally provisioned trust policy need portable
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
to run these comparisons; it includes the pinned passport crypto closure. The hosted
job explicitly imports both schema and crypto backends before running. The runtime
comparison must authenticate a known-good fixture and reject negative fixtures for
their expected reasons; an unavailable or always-rejecting backend cannot pass it.
