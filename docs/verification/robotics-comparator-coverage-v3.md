# Passive comparator coverage review v3

Routing review baseline: `e296382529b9f59e25f56c077e679bbba610e16b`.
This is a finite synthetic evidence review, not complete receiver equivalence or
a production KEEP/MIGRATE decision. No runtime adapter or driver changed.

The original wire corpus edits sender/component header bytes without updating
CRC. Those cases establish rejection of those bytes but do not independently
establish routing-filter enforcement. Two additive fixtures, named
`v3_sender_valid_crc` and `v3_component_valid_crc`, use the pinned SDK encoder
with a different system or component ID. The same packet is accepted with its
matching route and rejected as `sender_mismatch` by the ordinary `(1, 1)` route.
Acceptance remains unverified and perception-ineligible. CRC validity does not
authenticate the sender.

The original 17 fixtures remain identical, including their names and bytes.
At that revision the wire harness runs 19 cases. The native harness inherits both additions
through its existing wire-corpus composition: 35 cases/67 steps, with no new Rust
execution claimed here. The separate managed lifecycle corpus remains 16 cases/
48 steps. Historical receipts retain their original corpus and source hashes;
their passes do not cover these new fixtures.

| Contract property | Evidence scope after this correction |
| --- | --- |
| Two message layouts, zero trimming and finite values | Existing wire cases; finite examples only |
| Bad CRC and framing rejection | Existing wire cases; not an exhaustive malformed-input proof |
| System/component routing filters | New CRC-valid negative fixtures plus matching-route positive controls |
| Expiry, close, clock rollback, sequence/boot transitions | Existing lifecycle corpus; managed execution and historical native execution have separate receipts |
| Raised supplied-clock exceptions and cancellation | Dedicated Python receiver tests; absent from the cross-language corpus |
| Caller-owned snapshots and exact object disposal | Dedicated diagnostic inspection; absent from the cross-language corpus |
| Full constructor validation, signed replay, UDP and installed dependency equivalence | Not established by the comparator corpora |

The [source-bound receipt](robotics-routing-coverage-v3.json) records two RED
assertions for the absent fixtures, 41 passing focused harness methods, and the
normal/sanitized C run. A temporary audit-driver copy removes only the routing
checks. Under the existing typed/numeric comparator, that copy passes all original
17 cases but fails both additions. The repository driver is unchanged. This
negative control demonstrates test discrimination; it does not report a defect
in the production receiver or authorize a transmit path.

The initial negative-control inspection used exact dictionary equality and failed
on C's decimal rendering of accepted binary32 values. The existing comparator
accepts those original values and rejects the two new admission mismatches. That
failed inspection is retained; no numeric tolerance or acceptance threshold was
changed. Incidental harness timings remain in the raw receipt without a runtime
ranking or deployment claim.

This fixture correction uses the existing SDK encoder and test harness. It does
not select a new technology or extend a candidate implementation. Missing target
constraints and unequal candidate work remain unresolved. The earliest passive
component decision stays PENDING; later component reviews remain incomplete.

## Compatibility-flag coverage supplement

Reviewed baseline: `dfc7edbd3625bca651a046380b7781113754fc98`.
The original compatibility-flag mutation also has an invalid CRC. Preserve that
case and append `v3_compatibility_flag_valid_crc`, rebuilding its checksum with
the pinned SDK CRC implementation and the ATTITUDE message's CRC extra byte.
A direct SDK decode accepts the packet, while the adapter rejects it as
`unsupported_packet`, with no samples and no perception eligibility. This tests
the existing diagnostic profile's zero-flag restriction. It is not a MAVLink
requirement: the [official serialization specification](https://mavlink.io/en/guide/serialization.html#compatibility-flags-mavlink-2)
allows implementations to ignore unknown compatibility flags. That narrower
profile must not be described as complete protocol compatibility.

All previous 19 fixture records are unchanged. At that revision the wire corpus contains
20 cases; generated native fixtures contain 36 cases/68 steps. No new Rust
execution is claimed; the separate managed corpus remains 16 cases/48 steps.
The [flag coverage receipt](robotics-flag-coverage-v3.json) retains the absent-case
RED assertion, 42 passing focused methods, and normal/ASan/UBSan C parity. It also
retains an initial test-command import error caused by naming a nonexistent
managed test module, followed by the corrected invocation.

A temporary C audit-driver copy removes only the `p[3]` guard. The unchanged
comparator accepts its first 19 results but rejects its acceptance of the new
case. The repository driver and production receiver remain unchanged. This
isolates a local admission-policy check; it does not establish exhaustive header
coverage, signing safety, authenticated provenance or full runtime equivalence.
Incidental timings remain in the receipt without a performance ranking.

This is a correction to existing offline experiment fixtures, using the installed
SDK to encode/check its own wire contract. It introduces no runtime technology.
The production technology decision remains PENDING and later components remain
unreviewed. Remaining old header mutations should not be interpreted as isolated
checks: the unknown incompatibility flag and unsupported message also alter CRC;
the signed-flag mutation also lacks its signature trailer; and the v1 marker
mutation is not a valid v1 frame.

## Remaining header controls

Reviewed baseline: `bc2112d0cc7907b987885f91f3e0fa7ff98c8065`.
Four additive cases correct the remaining misleading header-coverage inference.
All earlier 20 records remain byte-for-byte identical; current wire coverage is
24 cases. None of these fixtures opens a connection or invokes a send method.

| New fixture | Independent fixture checks | Passive adapter result |
| --- | --- | --- |
| `v3_v1_valid_frame` | SDK-encoded v1 frame, correct v1 length/CRC, direct SDK decode | `unsupported_packet` |
| `v3_signed_valid_frame` | SDK-encoded v2 frame with full 13-byte trailer, correct CRC, direct SDK decode with one good signature under a public synthetic test key | `unsupported_packet` |
| `v3_unknown_incompat_valid_crc` | Correct v2 length and rebuilt CRC, incompatibility flag value 2 | `unsupported_packet` |
| `v3_heartbeat_valid_frame` | SDK-encoded HEARTBEAT with its own layout and CRC extra, direct SDK decode | `unsupported_message` |

The [MAVLink serialization specification](https://mavlink.io/en/guide/serialization.html)
defines the distinct v1/v2 headers, optional signature trailer and rejection of
unknown incompatibility flags. CRC correctness does not make the unknown-flag
case protocol-valid. The [pymavlink signing API](https://mavlink.io/en/mavgen_python/message_signing.html)
is used only to construct and check an offline fixture; the key is an openly
specified byte sequence, not deployment key material. This does not review or
qualify the separate signed receiver, persistent replay protection or source
identity. Production adapters and all candidate drivers are unchanged.

The new Python control first populates a receiver with an ordinary ATTITUDE
packet, then checks that each rejection withdraws all samples and returns
UNKNOWN with perception eligibility false. The C wire experiment continues to
compare only fresh-packet admission and decoded values. Its two-message SDK can
also reject HEARTBEAT independently of the outer allowlist. Likewise version,
signature and length restrictions can overlap. These results therefore do not
prove that every individual candidate guard is necessary or complete.

The [source-bound receipt](robotics-header-coverage-v3.json) records four expected
absent-fixture RED assertions, 43 passing focused methods without skips, Ruff and
Bandit checks, and normal/ASan/UBSan parity over 24 cases. Native input constants
were generated for 40 cases/72 steps; no new Rust execution is claimed. The
managed lifecycle corpus remains 16 cases/48 steps. Incidental benchmark values
are retained without a runtime ranking. Historical receipts remain bound to their
older source revisions and corpora.

The existing Python SDK test harness is retained for this fixture correction:
its purpose is to exercise the installed SDK API and the current Python object
boundary. Using a C, Rust or Kotlin wrapper would still require those same calls
to establish this evidence. This scoped tooling choice does not settle the
production technology decision, which remains PENDING. No forward feature
expansion or full-lane audit completion follows from the corrected finite corpus.

## Clock exceptions and audit cancellation receipts

Reviewed baseline: `1d77b03c0d33b1de60a9103646ca93b999a263d0`.
The lifecycle fixture format supplies a `now` value for each operation. It does
not invoke a failing clock callback in the JavaScript or Rust candidates. Invalid
clock values and rollback cases therefore cannot establish exception propagation,
cancellation or physical operator-stop behavior across those runtimes. No fixture
or driver changes in this correction extend that claim.

A separate executable reporting mismatch was found: both lifecycle audit runners
caught `Exception`, while the existing `finally` wrote a failed receipt after a
`KeyboardInterrupt`, `SystemExit` or `asyncio.CancelledError` without recording its
failure category. They now catch `BaseException` only to set `failure_type`, then
re-raise the original object immediately. No message, traceback or exception
arguments are added to the receipt. The existing final write remains best-effort
Python cleanup, not evidence of durability under process kill or storage failure.

Python documents the [cancellation hierarchy and need to re-raise](https://docs.python.org/3/library/asyncio-exceptions.html#asyncio.CancelledError)
and the [system-exiting exception hierarchy](https://docs.python.org/3/library/exceptions.html).
This correction stays in the Python orchestrators because it records Python
control flow around their existing compiler/process boundaries. A wrapper in C,
Kotlin, JavaScript or Rust would observe process exit status rather than preserve
the same in-process exception object. This is a scoped tooling decision, not a
production receiver KEEP/MIGRATE result.

Two regression methods cover three exception classes in each runner. Injection
occurs at the managed runner's first child attempt and the native runner's compiler
probe boundary. They verify identity-preserving propagation, one attempt only,
failed/PENDING state, no parity claim, source bindings and omission of exception
arguments. Native execution remains false at this pre-compilation boundary. These
are injected exceptions, not OS signal-delivery or child-process shutdown tests.

The existing direct receiver clock-fault method now also tests `CancelledError`
for both ingest and snapshot, alongside its four prior exception classes. It
populates both slots, verifies immediate withdrawal before propagation, and proves
a recovered callback cannot revive the latched receiver. Production receiver code
is unchanged. This direct Python evidence remains separate from candidate parity.

The [source-bound receipt](robotics-cancellation-receipt-v3.json) records six RED
assertions, a final 30-method PASS with no skips, and lint/format/security checks.
An initial formatting failure is retained in the validation record. The real
managed parity method still runs the unchanged 16-case/48-step corpus; no native
compilation, full-suite, performance or deployment qualification is claimed.
The earliest runtime choice remains PENDING and signing/replay remains unreviewed.

## Closed lifecycle operation records

Reviewed baseline: `2ae36d82653276f0aa043dcb478c6cd0b4c0e33e`.
The Python oracle treated unknown operation names as snapshots. The Python/JS
paths also ignored additional operation fields; the native input generator
ignored extra fields and synthesized an empty payload for a missing ingest `hex`.
This could allow a malformed experiment to produce ordinary results.

The existing operation record now has explicit admission rules: a dictionary
with operation `ingest`, `snapshot` or `close`; exactly `op`, `now`, `hex` for
ingest and exactly `op`, `now` for the other operations. The Python oracle and
native fixture generator share a non-coercing check; the JS driver independently
enforces the same field presence and operation set. Unknown operations and record
shapes raise fixed audit errors. Clock and packet value semantics remain with the
existing paths: notably, boolean clock fixtures remain available to exercise the
receiver's invalid-clock behavior. This is not a complete JSON ingress validator.

For this small existing experiment contract, direct checks were selected over a
new schema runtime or cross-language validator process. [JSON Schema closed-object
rules](https://json-schema.org/understanding-json-schema/reference/object#additionalproperties)
and [Pydantic extra-field controls](https://docs.pydantic.dev/latest/concepts/models/#extra-data)
can express field rejection too. Their default permissive handling must be
configured explicitly. Here, direct operation/field checks preserve the supplied
clock test objects and fixed error surface without adding serialization or another
runtime to the experiment. The decision is scoped to fixture admission, not a
production receiver language choice. No speed or memory advantage is claimed.

The [source-bound receipt](robotics-operation-record-v3.json) records 12 RED
assertions across Python reference, real Node driver and native fixture-generator
checks, followed by 31 passing focused methods without skips. Python lint/format,
Bandit and Node syntax checks pass. Comparing with the reviewed HEAD confirms all
16 lifecycle cases/48 steps and their reference outputs are unchanged. The native
40-case/72-step corpus and generated Rust constants are also unchanged; there was
no new Rust compilation. The managed parity test still runs its real candidate.
Production telemetry and the Rust/C decoder drivers are unchanged.

This correction validates operation records after JSON has been decoded. It does
not establish duplicate-member rejection, canonical clock/hex syntax, complete
case/root shape validation, callback-exception equivalence, or full lifecycle
qualification. Those boundaries remain distinct. The earliest production runtime
decision stays PENDING and later component reassessments remain incomplete.

## Reference CLI JSON admission

Reviewed baseline: `6431785214edccab56765467fc367401dbeb3c28`.
The `--reference` entry point used the default JSON parser after a 65,537-character
read. Duplicate keys silently selected the last value; JSON non-finite extensions
and overflowed floating values reached experiment execution. A valid document
padded beyond the intended input limit, a trailing suffix beyond the read window,
and a multibyte document larger than 65,536 bytes could still produce results.

The CLI now reads at most 65,537 bytes from its binary standard input, rejects
more than 65,536 bytes before parsing, explicitly decodes UTF-8 and reuses the
existing duplicate-member and finite-number hooks from result admission. Valid
boolean clock fixtures and wide integer timestamps are preserved. The existing
parent subprocess timeout remains ten seconds; this change adds no independent
CLI input deadline. The byte cap is an experiment input limit, not a new frozen
physical or telemetry threshold.

[Python's JSON documentation](https://docs.python.org/3/library/json.html#repeated-names-within-an-object)
describes last-value handling and the `object_pairs_hook`, `parse_constant` and
`parse_float` customization points. For this existing Python reference process,
reusing those hooks provides duplicate visibility before dictionaries discard it.
Post-decoding schema validation alone cannot recover discarded duplicate keys.
This small parser correction is not a production language KEEP decision, a
performance comparison or a replacement for the open runtime reassessment.

The [receipt](robotics-reference-json-v3.json) records nine expected RED assertions
(two duplicate-member inputs, four non-finite numbers, three oversized inputs),
then 34 passing lifecycle/native harness methods without skips. Positive CLI
checks preserve all original 16 cases/48 steps and compare the exact reference
results both at ordinary size and padded to the inclusive 65,536-byte boundary.
Ruff, formatting and Bandit pass after one initial formatting correction. Real
Node parity still runs; no new native compilation or timing ranking is claimed.

Case/root shapes, complete field-value admission and independent managed JSON
input rejection are not established here. The managed driver still uses
`JSON.parse`; this Python CLI correction must not be described as cross-runtime
duplicate-member parity. Production receiver code and all candidate drivers are
unchanged. The production runtime decision remains PENDING.

## Lifecycle case envelopes

Reviewed baseline: `4689c771f14f398e5b09ef89224a8a51c2ee21af`.
The reference accepted empty arrays/objects as experiments, ignored missing or
extra case metadata, and did not apply the native generator's case/step bounds.
The JavaScript driver allowed empty arrays and ignored case names. This could
produce ordinary comparison results for no work or ambiguous labels.

All three paths now require a list of 1–64 cases. Each case has exactly `name`
and `steps`, with a nonempty string name unique within the experiment and a list
of 1–64 steps. Python reference and native preparation share a preflight check;
JavaScript implements it independently. Every case envelope is checked before
any receiver is created. This aligns the existing native work bounds; it does
not change physical thresholds, packet policy or clock-value semantics.

The existing direct checks remain suitable for this small audit envelope.
[JSON Schema array constraints](https://json-schema.org/understanding-json-schema/reference/array#length)
can express list lengths, but name uniqueness across objects also needs an
explicit projected-name check. Here a bounded set and exact field checks preserve
input types without a second schema runtime in the measurement process. This
is a scoped correctness correction, not comparative performance evidence or
a production-language KEEP decision.

The [receipt](robotics-case-envelope-v3.json) retains 23 expected RED assertions
across reference, native generation and actual Node invocation, then 37 passing
focused methods. Inclusive 64-case and 64-step tests pass. A mocked receiver
confirms invalid later case envelopes are rejected before execution. An interim
test fixture accidentally reused a name and exercised the wrong rejection; that
failed run is retained, and the corrected fixture uses a distinct name. Existing
negative clock/packet tests now supply valid named envelopes so they still reach
the intended rejection. Oversized CLI tests use otherwise-valid cases and assert
the size error to avoid false positives from the new empty-case rejection.

All original 16 lifecycle cases/48 steps, reference outputs and 40-case/72-step
native generated inputs are unchanged. Ruff, formatting, Bandit and Node syntax
checks pass; three envelope methods were rerun after formatting. No new native
compilation, hardware qualification or timing ranking is claimed. Operation value
domains and independent JavaScript duplicate-member rejection remain separate
boundaries. Production runtime selection and later-component review are pending.

## Lifecycle operation value domains

Reviewed baseline: `71b401b1f5eb0daab6b9a7c051909e13c0b81a61`.
The native generator already required unsigned ASCII decimal clocks fitting u128
and at most 640 packet-text characters. Python reference and JavaScript admission
did not enforce that domain. Conversion behavior also differed: Python hex
decoding ignores ASCII whitespace, while Node hex conversion can silently truncate
at invalid characters or an unmatched trailing digit. These defaults could alter
the experimental input instead of rejecting it.

All comparison operation checks now accept a boolean invalid-clock sentinel or
an ASCII decimal string of 1–39 digits with numeric value below 2^128. Leading
zeros remain accepted within the length bound. For ingest, `hex` must be a string
of 0–640 ASCII hex digits in complete byte pairs; both cases are accepted, with
no whitespace, prefix or partial byte. Validation happens before numeric/byte
conversion. Python native preparation consumes the same validator as the oracle;
JavaScript independently implements these predicates. The native timestamp
emitter no longer duplicates the shared checks.

These are audit fixture domains, not production clock or packet thresholds. The
320-byte fixture maximum deliberately exceeds the receiver's 280-byte packet
limit so negative packet tests still reach receiver rejection. Empty packet and
boolean clock fixtures also remain valid experiment inputs. Production Python
clock integers are not restricted to u128 by this change.

The [Python bytes documentation](https://docs.python.org/3/library/stdtypes.html#bytes.fromhex)
and [Node Buffer documentation](https://nodejs.org/api/buffer.html#buffers-and-character-encodings)
explain why conversion alone is not common validation. Direct length, alphabet
and numeric-range checks establish the existing small experiment domain before
conversion; a new schema runtime would still require equivalent predicates.
This correction adds no production runtime winner or comparative speed claim.

The [receipt](robotics-operation-values-v3.json) retains 29 expected RED assertions
and 39 passing focused methods. Boundary controls cover maximum u128, leading
zeros, both booleans, empty hex and mixed-case 320-byte input. Python/Node outputs
are compared; native input constants are inspected without claiming compilation.
All original 16 lifecycle cases/48 steps and reference outputs are unchanged;
the combined 40-case/72-step generated native fixture is byte-identical. Ruff,
formatting, Bandit and Node syntax checks pass.

This does not establish independent JavaScript raw JSON admission, bounded stdin
allocation, actual Rust execution at this revision, arbitrary clock-callback
parity or hardware timing. Production adapter code is unchanged, runtime
reassessment remains PENDING, and later components remain unreviewed.

## Managed CLI byte admission

Reviewed baseline: `17b8ca0bb6e189259e94d5fd56795c793f14867e`.
The independent JavaScript comparison driver used `readFileSync(0)` and applied
its 65536-byte input limit afterwards. An oversized input was fully consumed;
implicit Buffer decoding also replaced invalid UTF-8 before JSON parsing. These
are experiment boundary defects, not production telemetry packet defects.

The driver now reads into a single 65537-byte buffer and rejects immediately when
the extra sentinel byte arrives. Each read is limited to the remaining capacity;
short reads continue until EOF or overflow. Only the initialized prefix is decoded.
Fatal UTF-8 decoding rejects malformed sequences, and BOM preservation lets JSON
parsing reject a leading BOM, matching the Python reference CLI.

For this small synchronous audit subprocess, bounded
[Node readSync](https://nodejs.org/api/fs.html#fsreadsyncfd-buffer-offset-length-position)
provides explicit destination size and byte counts. A stream/chunk accumulator
would require equivalent aggregate bounds and additional retained chunks; a new
runtime or parser would not remove that requirement. The standard
[TextDecoder options](https://nodejs.org/api/util.html#new-textdecoderencoding-options)
provide explicit error and BOM behavior. These choices repair the existing
candidate experiment and do not establish a production KEEP/MIGRATE decision.

The [receipt](robotics-managed-input-v3.json) retains two expected RED failures:
the old driver consumed 69633 rather than 65537 bytes of a small temporary file,
and accepted an invalid UTF-8 name. Valid ordinary and exactly 65536-byte inputs
preserve Python/Node lifecycle parity, including a multibyte label. A wrapper
using Node's builtin export synchronization forces reads of at most 17 bytes;
the real driver preserves corpus results and makes multiple reads. A separate
negative control preserves BOM rejection. The unchanged original corpus is also
covered by the existing managed parity test.

59 focused audit methods pass; the four input methods pass again after resolving
four initial Bandit partial-executable-path warnings by resolving Node explicitly.
Ruff, formatting, Bandit and Node syntax checks pass. Raw input allocation is
bounded, but this is not a whole-process memory limit or independent stdin
deadline: the invoking audit runner retains its subprocess timeout. JavaScript
JSON duplicate-member rejection remains unresolved. There is no new Rust run,
hardware latency result, production qualification or completed lane reassessment.

## Managed JSON member uniqueness

Reviewed baseline: `367db5022e08d0858474ddcd68670441a8769bb0`.
The managed driver parsed input with standard `JSON.parse`, which overwrites
earlier repeated members. That allowed a repeated operation or clock field to
change meaning before the experiment's strict field checks. The Python CLI's
object-pair hook already rejects this input; the managed CLI did not.

The [ECMAScript JSON specification](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.parse)
defines overwrite behavior. [RFC 8259 sections 4 and 8.3](https://www.rfc-editor.org/rfc/rfc8259)
explain duplicate-member interoperability and comparing decoded member names.
Schema validation or a reviver over the resulting object cannot restore the
lost member occurrences. A full replacement parser or external parser dependency
would add grammar responsibility to this small comparison driver. Instead, the
standard parser establishes valid JSON syntax, then an iterative token scan of
the original bounded text checks member uniqueness before using the parsed value.
This repair is scoped to experiment admission, not production language selection.

Whole JSON string tokens are consumed together, so their braces, colons and
escaped quotes do not affect structure. A stack holds a Set for each object and
an array marker for each array. In already-valid JSON, every colon follows a
member-name string; decoding that token with JSON.parse makes escaped and literal
spellings comparable. Sets avoid treating inherited property names as special.
The scan uses no recursion and does not collect the full token stream. Its input
remains limited to 65536 bytes by the prior byte-admission correction. This is not
a whole-process memory or execution deadline guarantee.

The [receipt](robotics-managed-duplicates-v3.json) retains ten expected RED
assertions across repeated name, steps, op, clock and hex members, escaped-key
aliases, a nested duplicate and special property names. Seven cases previously
succeeded; three were rejected later for schema errors instead of recognizing
duplicate input. All ten now fail with the fixed duplicate-member category and
no stdout. Positive controls preserve escaped unique keys, JSON-looking string
contents, both Unicode encodings, property order and separate object scopes.
The existing corpus and maximum-size/short-read input checks remain green.

61 focused audit methods, Ruff, formatting, Bandit and Node syntax pass. No
production adapter, native candidate execution or benchmark ranking changes are
claimed. Earlier timing records remain tied to their recorded source revisions.
The first-component production technology decision remains PENDING, with signing
and replay the next later unreviewed component.
