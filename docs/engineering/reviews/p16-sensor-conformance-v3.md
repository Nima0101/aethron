# P16 consumer review of published P2 image packets

Baseline `a3c9a815d8c81717dd58fd5b4ce47f50bad174c9`, reviewed 2026-10-10.
Decision: **KEEP P16 byte binding; FIX P2 consumer conformance coverage**.
No production defect or new decoder is asserted. The previous bridge's seven hashes,
parent and noreply identity match; it is published on PR 35 at this baseline.

## Constraints and technology decision

This is an offline, bounded conformance consumer of the actual P16 and P2 Python APIs,
not a sensor ingestion service. It must authenticate immutable layout and pixel bytes,
exercise the producer's real decoder, preserve unknown/failed outcomes and distinguish
authentication from content validation. Inputs are analytical two-pixel depth examples;
no device, personal data, live clocks or performance SLA is involved.

| Candidate | Decisive properties |
|---|---|
| Python direct public APIs with portable JSON vectors | Executes the existing P16 verifier and producer decoder together without a duplicate parser or subprocess protocol. Producer Pydantic models use [strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/); these tests call the actual implementation rather than assuming every constraint is expressible in JSON Schema. |
| TypeScript/Node consumer plus API subprocess | Credible for independently testing transport or client behavior. For this in-process API contract it adds IPC while still needing both Python APIs; it would test a different boundary. No speed ranking is claimed. |
| Kaitai Struct with generated native/JVM decoder | [Declarative binary format compilation](https://kaitai.io/) is a credible option outside the component's current languages for an independently owned binary protocol. Here it would create a competing decoder and would not execute the published P2 validators. |

KEEP direct Python calls and language-neutral vectors for this scope. The decision
follows the requirement to test real public APIs, not installation, familiarity or
rewrite cost. Producer technology is owned by P2; this review does not select or migrate
it. An independent transport service would require its own technology decision.

## Source and negative evidence

Packet implementation and both package initializers match protected main
`a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46`; the corpus pins all three hashes and tests
verify the imported module path. These are direct project inputs, not whole-environment
attestation. The local replay implementation and P2 prose differ from that main snapshot.
The initial source comparison assertion exposed the replay mismatch; neither file is
used as a published implementation in these tests. No peer-owned file is changed.

The five new test methods first failed on the missing portable corpus: five assertion
failures and zero errors. After publishing the corpus they exercise real Ed25519 binding
and producer decoding. Changing scale from 0.002 to 0.004 changes the decoded value while
preserving pixels, but breaks the existing evidence binding. Changed pixels also reject.
A newly signed truncated payload binds successfully with retained `failed` outcomes,
yet the real decoder rejects it. Newly signed zero samples bind with `unknown` outcomes
and decode to missing depth. All P16 authority/qualification flags remain false.

Only public RFC 8032 test-key material is used. No runtime, frozen threshold, physical
claim, calibration, replay or time mapping is added. Pydantic dependencies are isolated
in the optional Python 3.13 consumer requirements and dedicated hosted job. The workflow
triggers on consumed source changes. A source hash mismatch requires review; it is not
a reason to update a pin blindly. No hosted execution is claimed.

A main-tree path search found `evidence/phase1/p14.json`, which describes phase-1 server
work, not the assigned P14 scale/resilience contract. The existing producer handoff
remains open; independent P16 work continues. Whole-audit and lane completion remain false.

[Focused results and source bindings](p16-sensor-conformance-v3-results.json).

Validation: five consumer methods, 64 passport methods and 43 interop methods pass.
The first interop run retained one host thread-creation error; a sequential retry passes.
Ruff/actionlint initially also hit host thread limits. A subsequent import-order finding
and YAML plain-scalar quoting error were corrected before final lint/format/actionlint
success. P16 runtime Bandit, pip dependency consistency and whitespace checks pass.
