# P15 campaign reference byte binding v1

`qualification.campaign_references.bind(plan_bytes, domain_bytes, procedure_bytes)`
compares two caller-supplied byte strings to the domain and procedure hashes in
the [strict campaign plan v1](campaign-v1.md). It opens no files, devices or network
connections. The plan must pass the existing campaign plan schema and its 65,536
byte/depth-eight limits; no capture declarations are evaluated by this operation.

Each reference must be an exact built-in immutable `bytes` value, length 0 through
1,048,576 inclusive. Thus reference input is bounded by 2 MiB, excluding the plan.
Preexisting caller allocation is outside this function's budget. Mutable bytearrays,
views, strings and oversized values fail with fixed
`ValueError("invalid_campaign_references")`; invalid plan structure produces the
same error without input text. References are opaque and are never interpreted
as commands, paths, JSON approval statements or executable procedures.

The report contains exactly version `1`, `plan_sha256` of the original plan bytes,
`reference_counts` (`supplied`, `matched`, `supplied_bytes`), `reference_findings`,
`reference_bytes_verified`, `domain_verified`, `procedure_verified`,
`artifact_authenticity_verified` and `physical_qualification_passed`.
The last four fields are always false. Findings are fixed and sorted:
`domain_digest_mismatch`, `procedure_digest_mismatch`. Both failures are retained.
`reference_bytes_verified` means both byte strings match their declared hashes,
including empty strings when explicitly referenced. It does not establish useful
content, authenticity, preregistration, legal rights, domain suitability or a valid
physical procedure. Anyone able to replace the plan can replace its references.

Content and reference digests are not copied into the output. The plan hash and
aggregate sizes are linkable, not anonymization. A report is a mutable local result,
not a signature, durable receipt or authorization token; independent consumers must
verify the same immutable bytes themselves. Capture coverage, artifact binding,
trusted time and external domain/procedure approval remain separate gates. The
existing campaign evaluator's report and false verification fields remain unchanged.

## Technology decision — 2026-10-10

Requirements are a synchronous offline byte API, exact plan admission, immutable
inputs, at most two 1 MiB hash operations, minimized diagnostics and no deadline or
device SDK. Python/native hashlib directly combines strict plan validation with
immutable buffers and no reference payload copy. Rust owned buffers plus SHA-2,
Erlang/Elixir immutable binaries plus native crypto, C# with controlled backing
storage, and Node with owned snapshots are credible alternatives. The latter two
must distinguish read-only access from immutable ownership. None authenticates a
declared digest or proves reference semantics.

Select Python/native hashing for this boundary: the direct immutable representation
and shared strict plan admission meet the actual contract without a second byte
representation or additional parser. This is not based on installed tooling,
familiarity or rewrite cost. The retained [current ownership/hash experiment](technology/audit-tool-review-v3.json) checks four larger 1 MiB inputs in Python and
Node; it supports digest/ownership behavior, not a runtime speed ranking. Native
ABI or measured resource requirements would reopen the decision.

Primary sources inspected for this component:
[Python hashing and GIL release](https://docs.python.org/3.13/library/hashlib.html),
[Rust SHA-2](https://docs.rs/sha2/latest/sha2/), and
[Erlang crypto](https://www.erlang.org/doc/apps/crypto/crypto.html#hash/2).
The [artifact review](technology/review-v3.md#artifact-byte-binding-review) retains
the C#/Node ownership sources. No certification or real-time claim follows.
