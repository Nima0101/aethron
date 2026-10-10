# Robotics review v3 — incomplete

This is an implementation review record, not a replacement policy. Review starts
again at the passive MAVLink boundary at `52509c7`; v2 comparisons are historical
evidence, not v3 completion. No native runtime winner or migration is declared.

| Boundary | Current review state |
| --- | --- |
| Passive decoder, local receipt semantics and comparison evidence | In progress; FIX diagnostic retention, CLARIFY validation limits |
| Signing and replay journal | Not yet re-reviewed |
| Worker and IPC | Not yet re-reviewed |
| Provisioning | Not yet re-reviewed |
| Boot authority | Not yet re-reviewed |
| ROS SDK and DDS execution | Not yet re-reviewed |
| Versioned datagram wrapper | Not yet re-reviewed |
| Aggregate diagnostic | Not yet re-reviewed |
| Hosted ROS acquisition | Not yet re-reviewed |
| Vendor and simulated capability interfaces | Scope inventory remains open; no completion claim |

The passive implementation still labels samples `external_unverified`, leaves
capture time absent and perception eligibility false, and latches after local
clock rollback or closure. The reviewed tests assert these boundaries and reject
signed packets when no verifying key is present. These are software contract
checks; they establish neither physical acquisition age nor runtime deadlines.

A mismatch was found in the native comparison harness: its documentation claimed
failed diagnostics were retained, but subprocess timeouts and a failed compiler
version probe could raise before the logs were written. The harness now records
stdout and stderr as separate exact byte streams before propagating failure.
The same path handles the version probe, compiler and candidate process. Existing
10-second process/probe and 30-second compiler limits remain unchanged. Elapsed
measurement stops before log writing. Production receiver code is unchanged.

Two negative regressions failed before this correction: missing timeout logs and
missing compiler-probe stderr. The timeout case retains invalid UTF-8, CR/LF and
NUL bytes without text normalization; a real local failing executable checks the
compiler-probe path and failed-state receipt. Python documents byte-valued partial
output on [TimeoutExpired](https://docs.python.org/3/library/subprocess.html#subprocess.TimeoutExpired),
even when a caller requests text output. This repair uses that explicit exception
contract; it does not resolve the receiver's technology decision.

[Verification evidence](../verification/robotics-audit-failure-retention-v3.json)
records the focused results, including the separate JavaScript comparison timeout.
Prior C/JavaScript measurements remain limited comparisons. The native candidate
has no locally executed qualification; its presence in CI is not a passing result.
No hard-real-time, CNSA/MLS, availability, tactical deployment or hardware claim is
established here. The audit cursor remains at the first component until its
remaining evidence and technology questions are resolved.

## Hosted evidence inspection and JSON admission correction

The completed passive-wire job at `52509c7` supplied artifact `11655342381`.
The [retained review](../verification/robotics-native-hosted-review-v3.json) binds
its archive digest, workflow run, recorded source hashes and reproduced corpus /
fixture hashes. All eight Python/Rust output logs were independently decoded and
compared again against the production reference for 33 cases / 65 transitions.
The Rust checked and optimized profiles executed successfully on that hosted
runner. This supersedes any inference that the prototype had never executed;
it does not imply local Rust compilation or current-head hosted qualification.

The original JSON loader could silently discard repeated object members and
accept NaN/Infinity in metadata. This weakened the claim that candidate output
was faithfully checked. Four negative subprocess cases reproduced that gap.
The loader now rejects repeated members at every object depth and non-finite
numbers, including exponent overflow. Exact rejected stdout remains in the
failure logs. A positive case preserves boolean authority, decimal-string clocks
and binary32 values promoted to JSON numbers. Nine focused harness tests pass.
The repair uses Python's documented
[object-pair and number hooks](https://docs.python.org/3/library/json.html#standard-compliance-and-interoperability);
it introduces no new production runtime or transport.

Hosted timings and RSS remain in the original result with their limitations.
The native candidate embeds fixture inputs, fixes the sender tuple, omits signed
replay and packaging, and uses a finite integer-clock domain. Python imports the
full SDK and reads JSON input. These are different deployment envelopes, so this
review does not turn the comparison into a production speedup, hard-real-time
claim or unconditional language ranking. No production adapter was changed.
The first-component technology decision and later-component V3 reviews remain
open; no completion marker is justified.

## Passive API claim clarification

At `61cb81f`, the README example described a socket wait as `<=20ms` and stated
that `close()` erases state without identifying the owner of that state.
CLARIFY: the implementation configures a 20ms socket timeout; this is not a
measured upper bound on scheduling or complete `poll()` execution. Expiry runs
on `snapshot()`/`poll()` calls. The base adapter has no background watchdog.
A returned frozen `TelemetryStatus` holds immutable `Observation` objects, so
caller-owned references remain unchanged after later expiry or closure. Only
the decoder's own sample slots are cleared. The README now states these limits.

The evidence is `mavlink.py`'s `settimeout`, `poll`, `snapshot`, frozen dataclasses
and `close`, plus the existing provenance, independent-slot expiry and local
clock/closure tests. A bounded in-process check retained an old status through
expiry and closure and confirmed a new snapshot was UNKNOWN while the old
reference still held its original sample. This is evidence about API semantics,
not permission to retain a surveillance history or treat a saved status as live.
No production code, frozen threshold or transport behavior changes. This closes
the documentation mismatch only; the technology decision and review cursor remain
open. Existing timing failures and all hardware/deployment limitations remain.

## Managed comparison evidence admission

The independent JavaScript comparison still used the default JSON decoder after
the native harness correction. Five subprocess cases demonstrated acceptance of
repeated root/nested members and NaN, Infinity or exponent overflow in metadata.
FIX: reject those forms before typed parity comparison using the documented JSON
object-pair and number hooks already described above. A positive subprocess case
checks boolean provenance, a decimal-string clock beyond binary64's exact integer
range, and a finite fractional value. No receiver, runtime candidate or timing
threshold changed. This narrow repair does not choose a production technology.

[Focused evidence](../verification/robotics-managed-json-review-v3.json) retains
five initial failures and the subsequent 14 passing managed/native harness tests,
including actual execution of the existing managed comparison. This does not
rerun native compilation or qualify hardware. Historical comparison results are
unchanged. Managed subprocess failure-output retention remains a separate open
evidence issue; a passing corrected parser does not retroactively validate all
historical output. The first-component review remains incomplete.

## Managed failure-output retention

The preceding open retention issue is now corrected for the managed `run(out)`
path. Three failing cases showed missing logs after timeout, nonzero exit and
strict JSON rejection. The runner captures binary output and writes separate
stdout/stderr files before checking exit status or parsing JSON. Timeout partial
bytes are preserved without decoding; the original failure still propagates.
The report remains failed and records the attempted runtime/repetition and
exception type. No exception text or command arguments are copied into metadata.
Spawn failures before output exists can have a failed receipt without output logs.
Storage failure or abrupt process termination can still prevent retention.

Successful output uses the same path, with distinct files for all three pairs
and a reference JSON fixture. Hosted artifact configuration includes these files;
this is not a claim that the changed workflow has run. The process timeout stays
10 seconds. Elapsed measurement now stops before parent-side parsing/log writes;
older records included parent parsing and must not be compared as identical timing
measurements. No prior result is rewritten and no performance improvement is claimed.

[Focused evidence](../verification/robotics-managed-retention-review-v3.json)
records 16 passing tests, six retained/rechecked successful output pairs and the
initial failures/static findings. This is an evidence-integrity repair only, not a
production runtime decision or completion of the first-component V3 review.

## C comparison type fidelity and historical status

The earliest C comparison still used ordinary Python equality for metadata and
numeric closeness without a type check for sample values. Seven retained failing
assertions showed that this could accept numeric booleans, boolean sample values
and floating-point integer metadata. FIX: metadata must preserve the reference
JSON type; sample values must be finite integers/floats, excluding booleans. The
existing numeric tolerance is unchanged and equivalent finite sample numbers
such as `1` and `1.0` remain accepted. Python documents both
[cross-type numeric equality](https://docs.python.org/3/library/stdtypes.html#numeric-types-int-float-complex)
and [numeric closeness](https://docs.python.org/3/library/math.html#math.isclose);
neither alone establishes JSON type fidelity. This is a correction to the offline
checker, not a new runtime or a migration decision.

[Verification evidence](../verification/robotics-wire-types-review-v3.json)
binds the changed checker/tests, seven initial failures, 21 passing focused
harness methods and a bounded rerun of the unchanged 17-case C experiment. Normal
and AddressSanitizer/UndefinedBehaviorSanitizer builds pass the corrected parity
check. The new measurement receipt is retained separately; historical results
are not rewritten and no speedup or hardware claim is inferred.

CLARIFY: the v2 document now labels its native execution-pending section as a
preparation checkpoint and links the later hosted review. The wire corpus's
header mutations do not recompute CRC, so their rejection does not independently
prove each named header guard; the fixture names are not isolated guard coverage.
The C runner's JSON member admission and subprocess diagnostic retention have not
received the later managed/native corrections. Those evidence limitations remain
open, as do the first-component technology decision and subsequent V3 reviews.

## C comparison JSON admission and subprocess evidence

The preceding C JSON/retention issues are corrected for the offline `run(out)`
path. Five candidate documents with repeated root/nested members or non-finite
numbers previously reached a successful comparison receipt. Two subprocess cases
also demonstrated missing timeout/nonzero-exit logs. The loader now uses the
documented JSON member/number hooks described above, and the process wrapper saves
binary stdout/stderr before exit checking or UTF-8 decoding. Timeout partial bytes
are saved before the original exception propagates. Compiler, candidate, sanitizer
and compiler-version calls use distinct log names. The failed receipt records the
stage and exception type without copying command arguments or raw exception text.

The same bounded corpus and numeric tolerance remain. Compiler/candidate timeouts
remain 30/5 seconds. The reference output and input corpus are retained alongside
process logs, and the hosted upload configuration now includes these artifacts.
This does not claim that the changed workflow has run. The artifact directory must
still be new; storage failure, abrupt termination or process-spawn failure can
prevent complete logs. In-process Python generation errors are not subprocess
output and are not covered by the wrapper's binary-log claim.

[Evidence](../verification/robotics-wire-json-retention-review-v3.json) retains
the initial fixture mistake, seven corrected RED assertions, 25 passing focused
methods and normal/sanitized execution of the unchanged 17-case experiment. Five
output pairs were retained and both candidate logs independently parsed and checked
against the reference. Real local fixture processes also verify rejected JSON and
invalid UTF-8 retention. No production receiver, candidate decoder or frozen bound
changed. The new receipt is separate from historical measurements; no performance
ranking is inferred. This resolves these evidence defects, not the open technology
decision, isolated-header-guard coverage or complete V3 review.

## C benchmark summary consistency

The C runner validated decoded packet results but copied benchmark metadata without
checking it. Twelve negative fixtures returned successful comparison receipts for
missing/extra fields, wrong probe or acceptance counts, boolean/float/negative or
overflowing timing values, unordered percentiles, or an inconsistent sanitizer
summary. FIX: both profiles now require the five declared integer fields, unsigned
64-bit values matching the driver's representation, exactly 512 samples and the
acceptance count independently computed from the fixed round-robin reference
schedule. Timing summaries must satisfy `p50 <= p95 <= max`. Zero durations remain
valid; clock resolution can make a measured interval zero. No new performance
threshold or sample schedule is introduced.

[Evidence](../verification/robotics-wire-metadata-review-v3.json) retains the
twelve RED failures, 27 passing focused tests, a successful zero-duration control
and normal/sanitized execution of the unchanged 17-case experiment. Both retained
candidate logs also passed a separate parity/metadata recheck. Initial formatting
findings were corrected and retained in the record. Production receiver and
candidate implementations are unchanged.

These checks establish internal summary consistency only. Ordered integer numbers
do not prove that a candidate measured them honestly, authenticate the host clock,
or recover individual timing samples. Historical reports are not retroactively
qualified by this correction. Resource/latency comparisons still have different
deployment envelopes; no runtime winner or complete first-component review follows.

## Lifecycle measurement metadata admission

Managed and native comparisons checked result parity but copied unchecked RSS and
runtime metadata into successful reports. Twenty-five retained negative assertions
showed acceptance of boolean, negative, fractional, string or null RSS; missing
metadata; invalid runtime labels; and extra fields. The managed `compare` and
`run` paths and both native profiles now validate the declared report envelope
before copying measurements. A shared helper requires nonnegative integer RSS,
excluding booleans, and a nonempty string runtime label for Python/JavaScript.
The Rust driver has no runtime-label field; its compiler description remains in
the enclosing report. Exact field sets reject missing and undeclared metadata.
Zero RSS remains accepted without inventing a hardware-dependent lower bound.

This is a narrow offline evidence correction using the harness's existing typed
JSON boundary, not a new production component or a runtime selection. The fields
follow the unchanged drivers: Node documents integer
[maxRSS in KiB](https://nodejs.org/api/process.html#processresourceusage), while
Python exposes [getrusage integer fields](https://docs.python.org/3/library/resource.html#resource.getrusage).
These declarations do not authenticate reported values, verify a runtime label,
or establish portable RSS units. The current comparison was run on Linux;
platform-specific measurement behavior still needs separate qualification.

[Evidence](../verification/robotics-lifecycle-metadata-review-v3.json) records
25 RED assertions, 30 passing focused methods, three actual managed process pairs
and independent rechecks of their six outputs. The native report-admission tests
use controlled process results and do not execute Rust. Eight archived outputs
from hosted head `52509c7` also meet the new metadata shape; this is a historical
artifact recheck, not current-head native qualification. A test closure lint
finding was corrected and the ten native harness methods rerun successfully.

No production adapter, candidate implementation, corpus, timing threshold or
process timeout changed. Historical results remain unchanged. The technology
decision and earliest-component review remain incomplete.

## Receipt-clock scope and suspend qualification

CLARIFY the first component's receipt-age claim: `PassiveTelemetry` subtracts
values from its supplied clock, defaulting to `time.monotonic_ns()`. On the
reviewed Linux host, `get_clock_info("monotonic")` reports
`clock_gettime(CLOCK_MONOTONIC)`, monotonic true, adjustable false and resolution
1ns. Those are interface properties, not an accuracy measurement. Python also
states that the adjustable flag does not describe gradual rate adjustments.
The [kernel clock reference](https://www.kernel.org/doc/html/latest/core-api/timekeeping.html)
states that CLOCK_MONOTONIC excludes system suspension; Python distinguishes
[suspend-aware CLOCK_BOOTTIME](https://docs.python.org/3/library/time.html#time.CLOCK_BOOTTIME).
This review does not change clock sources, authority epochs or the frozen TTL.

The implementation checks nonnegative integer readings and rollback, then expires
samples only when the clock difference exceeds 100000000ns. It does not measure
clock rate or detect suspension. Therefore a receipt-age result is conditional on
that clock and cannot qualify elapsed age across suspend/resume. An unchanging
injected clock also cannot demonstrate real elapsed freshness merely by remaining
nondecreasing. The README now states these conditions next to the receipt TTL.
The earlier synthetic state comparisons exercise clock values; they provide no
physical oscillator, suspend/resume or scheduler qualification in any language.

[Source-bound evidence](../verification/robotics-receipt-clock-claims-v3.json)
records the local clock description and three passing existing provenance,
independent-expiry and rollback/closure tests. No new test freezes an unqualified
platform behavior. No host suspension, OS clock change, transport or hardware
experiment was performed. Production and test source bytes are unchanged.
This documentation correction narrows the claim; it does not select a runtime or
complete the first-component review. A language-only speed comparison cannot
establish the missing clock/deployment evidence.

## Comparison source bindings and current review label

FIX the three standalone comparison receipts: they still emitted
`audit_policy_version: 2` during the current review and did not bind the production
reference source. The native receipt also omitted the two Python helpers that
produce its combined corpus and reference. Receipts now label the review as 3 and
record a scoped `source_sha256` map before corpus generation or child execution.
The C and JavaScript maps contain the harness, original candidate and production
reference; the Rust map additionally contains both Python corpus helpers. Existing
harness/driver/fixture digest fields remain compatible. The version in filenames
identifies the historical experiment; it is not a completion marker.

This correction uses the existing byte-digest mechanism; Python's
[hashlib interface](https://docs.python.org/3/library/hashlib.html) accepts exact
file bytes and emits hexadecimal SHA-256 digests. Requirements here are a small,
portable JSON receipt and reproducible source identification, with no latency or
hardware claim. A Git HEAD alone would omit working-copy differences; a detached
shell hashing process would add process execution without identifying more inputs.
Neither improves this narrow correction. This does not settle the open production
language/runtime reassessment or introduce a new telemetry component.

[Source-bound results](../verification/robotics-source-manifest-review-v3.json)
retain 12 RED assertions and 31 passing focused methods, including source-map and
review-version checks for successful and failed receipts in all three harnesses.
Successful native receipt tests use controlled process results, not compilation.
Actual local C normal/sanitized and managed comparisons succeeded; the native
attempt failed because `rustc` is unavailable, and its failure receipt includes
all five source bindings. A separate recheck verified 11 digest entries across
those three new receipts. Host resource failures and the successful sequential
retries remain recorded. Production, candidate and corpus behavior is unchanged.

These maps identify selected repository bytes present when the run starts. They
are not signed attestations, a complete dependency manifest, proof of loaded
module origin, or protection against concurrent edits. Interpreter, SDK, compiler
and host qualification remain separate. Historical reports are unchanged and do
not acquire these bindings retroactively. No comparison winner, first-component
completion or full V3 completion follows from this correction.
