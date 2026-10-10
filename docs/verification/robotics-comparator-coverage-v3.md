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
