# P16 retrospective technology audit — policy 2

Historical baseline only. Current component reviews are indexed in the
[V3 inventory](../reviews/p16-p18-inventory-v3.md); this document does not establish
current implementation or whole-lane completion. The comparison probe now refuses
Python `-O`/`-OO` execution because those modes remove its evidence assertions.

Audit date: 2026-10-10. Baseline: `6bcf4730358c9626f4456036ac19252ef02e97c4`,
including the uncommitted envelope/policy schema increment. This replaces the older
technology rationale for the audited components. It does not change frozen contracts.
Walk order follows the two implementation commits, then the pending conformance work.
No task/federation/resource/transport implementation exists in this lane baseline;
those future components require their own technology decision. The shared
`_json_bounds` implementation predates this lane and remains a consumed P1 interface.

## 1. Passport parsing, canonicalization, authentication and trust policy — KEEP

Deployment constraints: synchronous offline software admission on Linux/macOS/Windows;
exact immutable input bytes; no network, subprocess, filesystem or clock reads inside
the verifier; 64 KiB per input, depth 8, one signature, at most 16 keys and 256 entries
per revocation list. No hard real-time deadline, embedded/no-allocator target, or
high-throughput service requirement has been supplied. These absences are not hardware
qualification. Public callers supply authenticated policy, subject, time and rollback
floors. Rejection semantics and no-authority output are mandatory across any migration.

The domain shortlist includes dynamic and compiled memory-safe runtimes and a native
library. An installed SDK is not a selection criterion.

| Candidate | Source-backed decisive properties | Fit for this component |
| --- | --- | --- |
| Python + cryptography | [JSON hooks](https://docs.python.org/3/library/json.html) expose object pairs and float/constant tokens before conversion; [Ed25519 API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) supplies raw-key verification and explicit failure. | Can reject duplicate keys and float lexemes without a second JSON lexer. Exact immutable bytes keep validation and signature input identical. Explicit type checks are still necessary. |
| Rust + Serde + ed25519-dalek | [Serde](https://serde.rs/container-attrs.html) supports closed typed structures; [dalek](https://docs.rs/ed25519-dalek/latest/ed25519_dalek/struct.VerifyingKey.html) exposes strict verification and documents weak-key differences. | Strong native ownership and typed parsing candidate for a standalone/embedded verifier. Backend rejection semantics require edge-case parity; changing to strict verification must not silently change the versioned acceptance set. No such deployment need currently establishes a material win. |
| TypeScript/JavaScript + Node crypto | [Node crypto](https://nodejs.org/api/crypto.html) supports Ed25519 verification. The executable probe below checks actual JSON and crypto behavior. | Native crypto is suitable. Default JSON decoding loses duplicate keys and floating-point spellings; an extra lexical parser is needed before policy admission. Not selected for this strict byte protocol. |
| Java/Kotlin + JCA + Jackson | [JCA algorithm names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html) include Ed25519; [Jackson streaming API](https://fasterxml.github.io/jackson-core/javadoc/2.14/com/fasterxml/jackson/core/StreamReadFeature.html) explicitly detects duplicate properties. | Credible managed alternative with streaming token access. It can meet the constraints, but does not remove custom canonical-byte, policy/time or scope checks. No evidence of a material safety advantage for this bounded profile. |
| C# + System.Text.Json | [.NET 10 duplicate-property option](https://learn.microsoft.com/en-us/dotnet/api/system.text.json.jsonserializeroptions.allowduplicateproperties?view=net-10.0) permits rejection rather than overwriting. | Credible managed parser candidate, not dismissed for being absent locally. A complete Ed25519 backend and lexical-token integration still need qualification; parser features alone do not establish a winning replacement. |

Decision: **KEEP Python with the maintained native cryptography backend**. The positive
advantages are direct lexical rejection hooks, immutable validation/signature inputs,
and an inspectable small policy evaluator without hand-written cryptographic arithmetic.
The current bounds demonstrably contain a token-dense adversarial input. Rust's ownership
and JVM/.NET typing are useful alternatives, but do not establish a material improvement
to this offline profile under the present deployment requirements. This is not a claim
that Python is fastest or universally safest. A no-runtime deployment, smaller memory
budget, sustained throughput target or measured bottleneck reopens this decision.

Executable evidence: `scripts/passport_technology_probe.py` invokes a separate Node
primitive probe with a 15-second timeout and one V8 worker. Six public signed fixtures
produce identical crypto results; five have valid signatures, but only one passes the
full admission contract. This includes a signed authority-escalation negative. Five
lexical/resource negatives are rejected by the Python parser. Node's default parser
collapses duplicate fields and `1.0`/`1e0`; that observation is not a claim that a custom
Node verifier cannot be correct. The existing 18 passport tests exercise schema,
canonicalization, backend absence, trust, revocation, expiry and rollback.

One Linux sample with Python 3.13.5 and Node 22.23.2: mean full verification 0.559 ms over
128 calls; token-dense 65,535-byte rejected input peaked at 412,019 Python-traced bytes.
This excludes native allocations and interpreter RSS. No competing full verifier was
benchmarked. The probe first timed out during host process exhaustion; the failure is
retained, and the one-worker retry passed. No threshold was altered to hide that failure.

## 2. Evidence byte binding — KEEP

Constraints: 1–16 exact immutable blobs, each at most 64 KiB; preflight all bounds before
hashing, then reauthenticate on every call. Match the entire signed digest set including
failed and unknown evidence. No content parsing, file opening, streaming mutable buffers,
cache, qualification or motion authority. Returned values retain only bounded metadata.

Candidates are Python/hashlib, Rust/sha2, Java/JCA MessageDigest, C# cryptographic hashing,
and Node/createHash. Each can compute SHA-256; native-language loop speed is not the
dominant algorithmic work. [hashlib](https://docs.python.org/3.13/library/hashlib.html)
already delegates hashing to native implementations, and exposes immutable digest
results. The Node probe independently agrees on the 64 KiB digest after hashing 1 MiB.
Single samples were 0.510 ms for Python and 1.268 ms for Node; setup differences and host
contention prevent a throughput ranking. Rust can enforce borrowing, whereas Java,
C# and Node byte arrays need an ownership/copy discipline to prevent concurrent mutation.

Decision: **KEEP Python/hashlib**. Exact `bytes` plus an exact tuple give the adapter an
immutable snapshot across reauthentication and digest comparison; no additional parsing
or mutable foreign-memory boundary is necessary. The expensive hash is already native.
No evidence demonstrates a material migration benefit at the frozen 1 MiB aggregate
bound. Seven adapter tests and eight portable vectors check byte substitution, missing,
extra and duplicate content, rollback/revocation revalidation and preserved negatives.

## 3. Portable schemas, vectors and conformance tooling — KEEP

Constraints: language-neutral structural contracts, no implicit network resolution,
closed shapes, explicit resource lengths, reproducible signature fixtures, and clear
separation between structure and authenticated admission. JSON Schema cannot recover
lexical duplicate fields or distinguish `1` from `1.0` after mathematical decoding.

Compare [JSON Schema 2020-12](https://json-schema.org/draft/2020-12),
[CUE](https://cuelang.org/docs/concept/how-cue-enables-configuration/) constraints,
and typed Serde/Jackson/.NET models. CUE's unification is attractive for configuration
constraints, but would require a translation boundary for consumers of this JSON
wire profile. Typed models bind the contract to a language and still need independent
lexical and signature validation. JSON Schema provides the direct cross-language
structural artifact this profile needs; none substitutes for the full verifier.

For the independent checker compare Python/jsonschema with JavaScript/Ajv.
[jsonschema registries](https://python-jsonschema.readthedocs.io/en/stable/referencing/)
allow explicit rejection of all external retrieval. [Ajv security guidance](https://ajv.js.org/security.html)
addresses trusted schemas and resource/regex constraints. Both can meet the task.
Decision: **KEEP JSON Schema and Python/jsonschema for this small offline test corpus**:
explicit registry isolation is executable, no generated validator code is needed, and
the six conformance tests separately expose schema/runtime semantic differences. Ajv
compilation would be a useful candidate for a measured high-volume validation workload;
no such workload is required here. Language familiarity and installation availability
are not the reasons for the choice.

Correct the existing identifier schema's final-newline acceptance; the observed RED
test demonstrates a real contract mismatch. The pending schema patch uses a portable
absolute-end assertion and adds envelope/policy shapes. It changes no runtime bounds.
Hosted tests require explicit crypto/schema imports so missing dependencies cannot
masquerade as success. Linux/macOS/Windows qualification remains hosted; local results
do not stand in for those jobs.

The audit harness itself uses Python for fixture orchestration and Node for an independent
crypto/parser observation, with no downloads or production dependency changes. This is
an intentional two-runtime measurement, not a second production implementation.

Reproduce: install the pinned passport and optional conformance test dependencies in an
isolated environment, run `python scripts/passport_technology_probe.py` with Node available,
then `python -m unittest discover -s tests -p 'test_passport*.py'`. The probe must fail
when Node is absent; a skipped comparison is not successful audit evidence.
