# Artifact byte-binding contract v1

`qualification.artifacts.verify(manifest: bytes, artifacts: dict[str, bytes],
*, now_ms: int)` checks caller-supplied immutable artifact bytes against the
references in a [v1 declaration](schema-v1.md). No file, device, URL, archive,
capture stream or network is opened. It returns only counts, fixed findings,
the input-manifest digest and the existing declaration report. No artifact
payload, raw digest key, sensor/device identifier or error input is echoed.

Limits, fixed before tests: the unchanged manifest byte/depth limits apply;
at most 15 artifact entries, at most 1,048,576 bytes per artifact and at most
4,194,304 supplied artifact bytes in total. Exact built-in `dict`, `str` keys
and immutable `bytes` values are required; keys are lowercase SHA-256 hex.
Empty bytes can be matched to their real hash but convey no physical evidence.
Malformed types, digests or budgets raise only
`ValueError("invalid_qualification_artifacts")`. Malformed declarations also
produce that fixed error. The API cannot bound memory allocated by its caller
before the call, and callers must not mutate the mapping concurrently.

Every distinct referenced digest must have matching bytes. Repeated references
share one artifact and are counted once. Missing, mismatched and unreferenced
artifacts produce independent counts and sorted fixed findings. A document
with no artifact references never receives a vacuous byte-verification pass.
All declaration findings, including expired calibration, remain present even
when every artifact digest matches.

The returned `artifact_bytes_verified` proves only equality to the declared
digests of supplied bytes in this call. `software_checks_passed` additionally
requires all declaration checks. `artifact_authenticity_verified` and
`physical_qualification_passed` are always false; the nested declaration
report's historical `artifacts_verified` field remains false. No contents are
interpreted as calibration or measurement truth. Subsequent consumers must use
the same immutable bytes or reverify; no filesystem snapshot is claimed.
Replacing a value in the caller's mapping after return does not update an old
report. Its nested input digest commits the declaration, not a separately
authenticated artifact collection or the evaluation instant. Retain the actual
verified bytes and evaluation provenance; the aggregate report is not a reusable
authorization token. Runtime/backend failures must not be treated as success.

Supply only authorized, minimized evidence. This API is not a privacy/rights
scanner, signed attestation verifier or live recording API. The input-manifest
digest is linkable, not encryption or anonymization. Existing synthetic fixture
hash placeholders intentionally cannot pass real byte-binding checks.

## Technology review

This component needs offline deterministic SHA-256, bounded work, exact byte
semantics, portable tests and no sensor/OS SDK or real-time scheduling. Large
capture/archive ingestion is a separate interface. The requirements permit a
small in-memory API without filesystem path/symlink or blocking-device access.

The [fresh component review](technology/review-v3.md#artifact-byte-binding-review)
compares ownership, trust boundaries and native hash implementations across
Python, Rust, Erlang/Elixir, C#, Node and Swift. It retains the current immutable
byte boundary with explicit budgets; no measured performance superiority is
claimed. Compilation or installation cost is not a reason to reject a candidate.

Implementation plan: first run missing-feature tests using known SHA-256
vectors and bounded malformed inputs; implement byte verification; then check
declaration parity, budget edges, deterministic reports, no input mutation,
privacy and negative-evidence retention with focused tests/lint/security.
