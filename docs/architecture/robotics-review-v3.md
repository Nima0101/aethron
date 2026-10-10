# Robotics review v3 — incomplete

This is an implementation review record, not a replacement policy. Review starts
again at the passive MAVLink boundary at `52509c7`; v2 comparisons are historical
evidence, not v3 completion. No native runtime winner or migration is declared.
Later sections record corrections; earlier source-bound findings remain historical.
The supplied-clock retained-sample gap is corrected in
[Supplied-clock exceptions withdraw retained samples](#supplied-clock-exceptions-withdraw-retained-samples),
without establishing general clock or hardware qualification.

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

## Supplied-clock exception negative evidence

RETRACT/CLARIFY any general interpretation of clock-fault latching at the first
passive boundary. `_now()` checks the type, sign and ordering of values returned
by its clock, but calls that clock before those checks and without an exception
handler. Python's [exception handling rules](https://docs.python.org/3/tutorial/errors.html#handling-exceptions)
explain propagation when there is no matching handler. The runtime source and a
bounded in-process probe confirm the distinction; this is not inferred from a
successful rollback test.

Two independent synthetic instances first admitted one packet at a fixed receipt
clock, then raised `RuntimeError` from the supplied clock during `snapshot()` or
`ingest()`. Both calls propagated the exception. After the clock resumed its
original value, each next snapshot still contained one `OBSERVED_UNVERIFIED`
sample with perception eligibility false. Explicit closure then returned UNKNOWN
with reason `closed`. The probe deliberately exited nonzero because general
clock-exception withdrawal/latching was not established. It used no socket,
vehicle, OS clock modification, timing benchmark or private data.

[Retained evidence](../verification/robotics-clock-exception-claims-v3.json)
records source digests, the exact synthetic conditions, both observed outcomes,
and three passing existing provenance/expiry/rollback methods. Those methods
cover different conditions and do not cancel this negative result. The README
now explicitly distinguishes returned invalid clock values from raised clock
exceptions. Production and test sources remain unchanged; this corrects the
qualification claim only. The failure-handling gap remains open, so no general
fail-closed clock claim, runtime KEEP/MIGRATE decision, first-component completion
or forward feature expansion is justified by this change.


## Executable reproduction of the clock exception receipt

FIX the reproducibility gap in the preceding negative evidence: synthetic
conditions and output were recorded, but the exact executable probe was absent
from the public tree. The [reproduction command](../verification/robotics-clock-exception-reproduction-v3.md)
now exposes the two in-process cases and unconditional cleanup. It deliberately
retains a nonzero qualification outcome, and explains why that exit code alone
cannot distinguish a reproduced observation from an execution error.

The code was extracted from the document and executed without a socket; its JSON
matched both historical observations exactly and stderr was empty. The extracted
code passed Ruff and Bandit. [Reproduction evidence](../verification/robotics-clock-exception-reproduction-v3.json)
binds the document, historical receipt, unchanged production source and this
review. Historical evidence bytes remain unchanged. This documentation addition
does not fix clock exception handling, select a production runtime, qualify any
hardware or complete the earliest component review.


## Measured Python baseline validation and cleanup

FIX the offline C comparison's measured reference path. Initial Python corpus
results were checked, but the 512 subsequent timed results were only counted.
Controlled changes to admission or numeric values therefore still allowed a
`compared` receipt. A raised exception also skipped that probe's `close()` call.
The measured path now applies the existing typed parity comparator after each
timed observation, and always closes the source in `finally`. Disagreement emits
a failed baseline receipt; it cannot inherit the earlier corpus's parity result.

This is a correction to an existing offline evidence harness, not a new runtime
component. The result and owning source are already in this Python process;
reusing its comparator avoids a second oracle or a cross-runtime conversion that
could erase type distinctions. The production runtime choice remains pending.
Python's [cleanup semantics](https://docs.python.org/3/tutorial/errors.html#defining-clean-up-actions)
provide the required cleanup on normal and exceptional paths. Validation and
cleanup remain outside the timed interval. That preserves the interval definition,
not comparability across runs or immunity from host scheduling.

[Source-bound results](../verification/robotics-measured-baseline-review-v3.json)
retain three RED assertions, 12 passing focused methods, and an actual local
normal/sanitized C comparison over 17 cases and 512 probes. Regression controls
use inert candidate outputs and a synthetic reference object to isolate report
admission and cleanup; the actual compiler run is recorded separately. The raw
Python maximum of 57,659,283 ns remains in the receipt. This is not a hardware
latency bound or a fair production-runtime ranking: C still omits the Python
reference's state and provenance work. Production adapter and C candidate bytes
are unchanged, the supplied-clock exception gap remains open, and the first
component review is not complete.


## Individual reference duration admission

FIX the offline C comparison's asymmetric timing admission. Candidate summary
fields already required unsigned integer nanoseconds, but the Python reference
could report `compared` after one negative, fractional or oversized duration.
A summary-only check is insufficient: sorting and selecting percentiles can hide
an invalid individual sample. Every measured reference duration now must be an
integer in the existing unsigned 64-bit report domain before it enters the
summary. Invalid duration produces `baseline_timing_failed`, retains the failed
baseline receipt and follows the existing unconditional source cleanup path.
Zero durations remain permitted; this does not claim a particular clock resolution.

Python documents [monotonic_ns](https://docs.python.org/3/library/time.html#time.monotonic_ns)
as integer nanoseconds and defines usable time differences rather than a fixed
epoch. The check therefore constrains elapsed duration, not the absolute clock
origin. Synthetic patched readings exercise the receipt boundary; they do not
show that the OS clock actually failed. This small check stays beside the existing
in-process measurement and typed comparator. A separate native/process validator
would add serialization without improving admission of these Python integers;
this correction does not resolve the production runtime reassessment.

[Source-bound evidence](../verification/robotics-baseline-timing-review-v3.json)
retains three failing assertions followed by 13 passing harness methods and an
actual normal/sanitized C comparison over 17 cases. Both measured paths recorded
92 accepted probes out of 512. The Python maximum of 53,603,333 ns is retained.
Timing validation is outside the measured interval. The C and Python work remains
unequal, so these diagnostics neither rank production runtimes nor establish a
hardware latency bound. Production and candidate code are unchanged; the separate
production clock-exception gap and earliest-component decision remain open.


## Lifecycle process timing failures preserve captured output

FIX the managed and native evidence harnesses' finishing-clock boundary. Both
read the ending clock before writing captured stdout/stderr; a raised exception
there discarded available diagnostic bytes. Both also admitted negative or
fractional process durations. Captured bytes now pass through `finally` retention,
and successful process results require a nonnegative integer duration before JSON
parsing. Zero duration remains admissible. Output writes and duration validation
stay outside the interval. An initial clock failure before process launch has no
child output to retain; filesystem write failures remain external I/O failures.

These are existing offline wrappers around fixed trusted commands. Local Python
cleanup and integer checks preserve the captured byte arrays without decoding or
an additional process. Moving validation into a candidate runtime would not cover
the parent clock or retention path. This bounded correction leaves production
technology selection pending. Python documents the relevant
[cleanup semantics](https://docs.python.org/3/tutorial/errors.html#defining-clean-up-actions)
and [integer monotonic clock](https://docs.python.org/3/library/time.html#time.monotonic_ns).

[Retained results](../verification/robotics-process-clock-review-v3.json) include
an initial run with four assertion failures and two missing-log errors, then a
clearer six-assertion RED run after adding explicit file-existence assertions.
All 24 focused methods pass, including unchanged timeout/nonzero-process checks
and new zero-duration controls. Fault regressions use controlled process results
and synthetic clock readings, not an OS clock fault or Rust execution.
The actual managed run compared three process pairs over 16 cases/48 transitions.
The native attempt failed with a missing compiler and `native_executed: false`.
The initial Bandit import warning is recorded; inspection confirmed fixed local
fixture argv and mocked results, and the native test import now carries the same
narrow rationale used by the other harness tests. No production adapter or
candidate code changed. The production clock-exception gap and earliest-component
review remain open; no qualification or completion claim follows.


## Native execution receipt uncertainty

FIX a negative-evidence ambiguity in the offline native harness. Previously,
`native_executed: false` remained after a candidate invocation failed during
output decoding, timeout handling, exit checking or finishing-clock handling.
Those failures do not establish that the candidate never ran. Report schema 2
adds `report_schema_version: 2` and `native_attempts` and gives `native_executed`
three explicit values:

- `false`: the native child wrapper has never been invoked in this run;
- `null`: at least one invocation was attempted, but none returned through the
  wrapper's exit, timing and JSON checks;
- `true`: at least one invocation returned through those checks. This does not
  establish measurement metadata validity, parity, or success of later attempts.

`native_attempts` counts calls to the native child wrapper, including failures
before process creation. It does not count confirmed process launches. A later
failure preserves earlier confirmation. Consumers must check the schema version
and distinguish `null` from `false`; Boolean coercion loses this distinction.
Unversioned historical receipts retain their original bytes and interpretation.
The existing `state`, `failure_type` and parity checks remain authoritative for
comparison success. An unknown execution value cannot yield a successful run.

The parent owns subprocess execution, timing and decoding. This bounded metadata
correction belongs in that parent; moving it to C, Rust, JavaScript or a schema
validator cannot observe parent-side failures reliably. It does not select a
production runtime or introduce a new component. Python's documented
[subprocess results and exceptions](https://docs.python.org/3/library/subprocess.html#subprocess.run)
separate completion, exit status and timeout; none alone establishes valid JSON.
The report deliberately retains uncertainty where the wrapper has not returned.

[Source-bound verification](../verification/robotics-native-execution-review-v3.json)
records eight RED assertions, then 26 passing focused methods. A fixed Python
stand-in executes through the actual child/JSON path and preserves malformed
stdout in a failed receipt with unknown execution. Compiler behavior is mocked
for this fixture: it is not Rust qualification. The actual local native audit
still stops at missing `rustc`, with zero native attempts and execution false.
An initial test import error from omitted `PYTHONPATH` and two corrected lint
findings are retained in the review record. Production and candidate sources are
unchanged. The production clock-exception gap, earliest-component technology
choice, subsequent components and overall lane completion remain open.


## Supplied-clock exceptions withdraw retained samples

FIX the production passive receiver's previously recorded supplied-clock gap.
`_now()` now clears its two retained sample slots and latches the existing
`local_clock_invalid` reason before re-raising an exception from the clock callable.
The same exception object propagates, including `KeyboardInterrupt` and
`SystemExit`. No failure detail is added to the returned status. Once latched,
subsequent calls neither consult the clock nor admit packets; recovery cannot
revive the failed session. Explicit close remains independent of clock access.
The 100 ms threshold, packet framing, provenance and public status fields are
unchanged. A caller's previously returned immutable snapshot is not erased.

This correction belongs at the Python callable/state boundary: the object owns
the samples and receives the exception. An external C/Rust/JavaScript validator
cannot guarantee this cleanup when that call raises before producing a value.
The bounded cleanup therefore stays here while the broader production runtime
choice remains PENDING. This is not an incumbent KEEP decision. Python documents
[BaseException and interruption semantics](https://docs.python.org/3/library/exceptions.html#KeyboardInterrupt)
and [cleanup before re-raising](https://docs.python.org/3/tutorial/errors.html#defining-clean-up-actions).
Catching only `Exception` would omit the interruption/exit controls; swallowing
them would interfere with operator cancellation. Cleanup immediately re-raises.

[Verification](../verification/robotics-clock-withdrawal-review-v3.json) retains
eight RED assertions: snapshot/ingest crossed with RuntimeError, OSError,
KeyboardInterrupt and SystemExit. Each begins with both sample slots populated.
The passing regression checks empty UNKNOWN, the fixed reason, exception identity,
no clock reread, no packet readmission and explicit close. The unchanged historical
reproduction now observes zero retained samples after both RuntimeError cases;
its deliberately unconditional negative exit and general-qualification flag are
preserved. Historical evidence files are not rewritten.

The focused passive/datagram/lifecycle suites pass. A broader attempted selection
also retained two environment errors: an isolated installed-package replay test
cannot import `aethron_edge`, and the boot-clock test module requires absent
Pydantic. These are not passes or exemptions; installed-package and boot-clock
verification remain unqualified in this environment. Bandit's existing deterministic
mutation-generator warning was inspected and narrowly annotated: it generates
parser test bytes only, never security entropy. No hardware test, real OS clock
fault, arbitrary interruption of cleanup, or exception in another adapter is
qualified. The comparator candidates do not implement Python callable exceptions;
existing finite-corpus parity does not cover this correction. The earliest-component
technology review and later components remain incomplete.


## Installed verification after completing local prerequisites

The [focused installed verification](../verification/robotics-installed-clock-review-v3.md)
resolves the preceding local import errors without changing their recorded results.
After installing the existing hashed Pydantic dependency subset and locally built
portable wheels, all 68 selected passive/signing/boot-clock/datagram/lifecycle tests
passed under an isolated parent interpreter. Four checked production modules were
loaded from site-packages and matched source bytes, including the clock-withdrawal
fix. The nested isolated fresh-process replay test also passed. No test was skipped
or weakened. The exact runner, source/wheel/log hashes and environment limitations
are retained. This is bounded verification of the existing fix, not a new component,
a production runtime decision, or full package/product qualification.

## Retain completed managed measurements when a later attempt fails

FIX the managed comparison receipt. Previously `runs` was attached to the final
report only after all six child processes succeeded. A failure in a later child
therefore discarded earlier validated timing/RSS metadata, including any slow
observation. Raw stdout/stderr survived, but parent-measured durations were not
recoverable from those logs. The report now owns the run list from initialization
and each pair before either child starts. Only results that pass metadata and
parity checks enter the pair. A partial pair is not a completed comparison:
`state` remains `failed`, `failed_attempt` identifies the failing child and no
overall `parity` success is emitted. Successful receipt fields remain unchanged.
Historical receipts are not rewritten. This is retention on handled failure or
normal Python unwinding, not crash-durable checkpointing or guaranteed recovery
after process termination, disk failure or power loss.

This is a correction in the parent that measures subprocess time, not a new
decoder or a production-language KEEP decision. Native or managed child code
cannot recover that parent's discarded measurement. The existing native harness
already attaches partial pairs before execution; its production code is unchanged.
The [source-bound result](../verification/robotics-partial-pair-review-v3.json)
records five RED assertions for later timeout, nonzero exit, malformed JSON,
invalid metadata and parity mismatch, followed by 27 passing focused harness
methods. Controlled process responses test the real receipt, timing, JSON,
metadata and parity paths; they do not qualify a compiler or SDK.

A real Python/JavaScript run also compared all 16 cases and 48 transitions across
three pairs. Observed whole-process times, in pair order, were Python
1,394,487,052 / 507,605,052 / 479,552,938 ns and JavaScript
693,002,043 / 116,501,463 / 115,798,864 ns. Reported peak RSS was 29,452 KiB
for Python and 45,812 / 46,324 / 46,328 KiB for JavaScript. All values, including
the slower first pair, are retained without an outlier exclusion. These are
shared-host whole-process observations, not isolated cold-import timings or
deadline guarantees. The pinned full Python dialect and the original two-layout
JavaScript prototype perform different dependency/import work. The
[official generator catalog](https://mavlink.io/en/#language-generator-list)
and [Rust SDK](https://github.com/mavlink/rust-mavlink) were revisited; SDK support
does not turn these original prototypes into SDK qualification. No numerical
deployment memory/startup budget is established. The earliest passive component
remains PENDING; signing/replay is the next later unreviewed component.

## Identify the SDK backend before interpreting startup costs

VERIFY the earliest passive decoder's dependency and startup boundary with the
[installed SDK probe](../verification/robotics-sdk-startup-v3.md). The pinned SDK
selects native CRC acceleration in the ordinary installed path and Python CRC
when the acceleration import is deliberately blocked. Both reject corruption
and preserve UNKNOWN/perception-ineligible semantics in the fixed synthetic
checks. Incremental import/constructor timings, peak RSS and loaded file hashes
are retained per process, including all slow observations. Installed dependencies
and actually imported modules are distinguished; no cold-machine, WCET, production
language winner or completed review is inferred. The safe-embedded addendum was
read at this checkpoint. Its non-actuating evidence requirements reinforce these
qualification limits and do not transfer P18/P19 ownership to this lane.

## Bind diagnostic provenance claims to accepted observations

The earliest passive-component evidence review found that the SDK startup
probe checked message names after acceptance, then checked perception eligibility
only after corrupt input emptied the status. Its unverified-observation claim
was not directly covered by that receipt. Schema 2 now exports the actual
accepted status and each sample's evidence/authentication/capture/signing metadata.
Both fixed unsigned fixture messages remain external-unverified, unauthenticated,
without capture or signing metadata, and perception-ineligible in both backend
modes. Tests assert false/null identities so numeric zero cannot substitute for
the boolean or null contract. No production adapter is changed.

The [source-bound results](../verification/robotics-sdk-provenance-v3.json)
retain two RED assertions, 14 passing focused tests, and both isolated receipts.
Historical schema-1 results remain unchanged and are identified by their commit.
This is an evidence correction using the existing interpreter probe, not a new
component, language selection or performance optimization. No source authorization,
sensor-fusion suitability, hard-real-time behavior or weapon integration follows
from passing these checks. The passive component's technology review remains
PENDING; signing/replay remains the next later unreviewed component.

## Consolidate the passive interface's assurance limits

CLARIFY the public telemetry entry point after re-reading the passive source,
its provenance/expiry/clock tests and the schema-2 receipt at `48de56c`.
Existing detailed prose correctly separated authentication from measurement
trust, but did not put the requested system-level assurance claims alongside
the introductory diagnostic contract. The README now maps acceptance, observed
status, receipt age and file hashes to their limited supported meanings. It
explicitly leaves cryptographic compliance, MLS, complete Zero Trust deployment,
availability and single-point-of-failure claims unqualified.

The official MAVLink serialization and message-signing guides were revisited
for the checksum/authentication distinction. No cryptographic implementation,
transport, receiver or runtime choice changed. The
[verification record](../verification/robotics-assurance-limits-v3.json) binds
the documentation and the focused existing checks; there is no invented RED
result or newly discovered production defect. This documentation review does
not advance the earliest component's PENDING technology decision or re-review
the later signing/replay, worker, ROS, vendor or simulated-interface components.

## Fresh earliest-component review: populated close evidence

Restarted the owner review at the passive receiver on `891066a`, reading current
policy, the safety/protocol/verification freezes, current source and prior receipts.
FIX the installed diagnostic probe's evidence coverage: its earlier close check
started from a receiver already emptied by corruption. Schema 3 now records close
from two populated slots and an attempted readmission, using a separate receiver
and real installed SDK in both CRC modes. Two RED assertions exposed the missing
receipt field; all 14 focused methods then passed with no skips. The production
receiver is unchanged. [Source-bound evidence](../verification/robotics-sdk-closure-v3.json)
retains both isolated receipts and all incidental observations.

The reviewed deployment constraints remain a bounded, optional Linux diagnostic
with two unregistered message layouts, no transmitter and no perception authority.
No target hardware, numerical startup/RAM budget, hard deadline or availability
qualification has been supplied. The [current MAVLink generator catalog](https://mavlink.io/en/#language-generator-list)
was revisited: C/C++, Rust, JavaScript, Python, Go, Kotlin and Clojure are serious
domain candidates; their catalog entries alone do not prove this receiver's
strict lifecycle/provenance behavior. Prior unequal prototype comparisons remain
limited evidence, not a production KEEP or MIGRATE decision.

This correction remains in the existing Python test probe because it observes
the installed Python object's returned states. A C, Kotlin or JavaScript wrapper
would still need to execute this object boundary to establish that behavior;
replacing the receiver would test a different implementation. The
[unittest assertion contract](https://docs.python.org/3/library/unittest.html#assert-methods)
supports identity checks for false/null values alongside state/sample checks.
This scoped test-tool choice is not a production language winner or a new adapter.
The earliest component remains PENDING; signing/replay is the next later
unreviewed component. No full audit marker, physical shutdown, weapon integration,
real-time, MLS/CNSA or customer qualification follows from these diagnostics.

## Isolate routing checks in comparator evidence

The [comparator coverage review](../verification/robotics-comparator-coverage-v3.md)
found that the old sender/component header mutations also invalidated CRC. Two
additive CRC-valid fixtures now isolate those routing checks. A temporary C audit
driver with routing guards omitted passes the old 17 cases and fails both new
cases under the unchanged comparator. Production code and repository drivers
are unchanged. The receipt preserves the initial inspection failure and incidental
measurements. This corrects a coverage gap without claiming complete behavioral
equivalence, a runtime winner or completion of the earliest component review.

## Isolate the diagnostic compatibility-flag policy

The next [coverage supplement](../verification/robotics-comparator-coverage-v3.md#compatibility-flag-coverage-supplement)
adds a CRC-valid compatibility-flag fixture. The SDK accepts it, while the
existing diagnostic profile rejects it. A temporary audit C copy missing only
that profile guard passes all previous 19 fixtures and fails the new fixture.
The unchanged driver passes 20 cases normally and with ASan/UBSan; 42 focused
methods pass. The [source-bound receipt](../verification/robotics-flag-coverage-v3.json)
retains the RED assertion and initial wrong-module invocation failure. This
strict local profile is narrower than MAVLink's permitted handling of unknown
compatibility flags. No production code, candidate driver, runtime decision or
qualification status changes.

## Separate valid controls from malformed header mutations

At `bc2112d`, the earliest passive-wire review found that the original version,
signing, incompatibility and message-ID mutations did not establish rejection
of otherwise correctly framed packets. Four [additive controls](../verification/robotics-comparator-coverage-v3.md#remaining-header-controls)
now exercise valid v1, fully signed synthetic v2, CRC-correct unknown-incompatibility
and valid HEARTBEAT packets. Tests verify the fixture properties and withdrawal
from a populated receiver; the C comparison remains fresh-packet-only. All prior
20 fixtures are preserved. Production and candidate drivers are unchanged.
[Retained evidence](../verification/robotics-header-coverage-v3.json) records the
four RED assertions, 43 passing methods and 24-case normal/sanitized C parity.
Native fixtures are generated only. This is a coverage correction, not a
production KEEP/MIGRATE decision or a review of signing/replay integration.

## Preserve audit cancellation categories

The [clock/cancellation review](../verification/robotics-comparator-coverage-v3.md#clock-exceptions-and-audit-cancellation-receipts)
confirms that supplied clock values in the comparison corpus do not prove raised
clock-callback behavior across languages. It also fixes a concrete evidence gap:
managed/native audit runners now record interruption and cancellation categories
before re-raising the same exception. Six RED assertions demonstrated omitted
categories; 30 focused methods pass after correction. Direct Python receiver
checks now include asyncio cancellation; production adapter and candidate drivers
are unchanged. [Evidence](../verification/robotics-cancellation-receipt-v3.json)
retains failure and validation records. The production technology reassessment
and subsequent components remain incomplete.

## Reject malformed lifecycle operation records

The [operation-record review](../verification/robotics-comparator-coverage-v3.md#closed-lifecycle-operation-records)
found silent unknown-operation fallback in the Python oracle and ignored operation
fields across comparison paths. Shared Python admission and independent JS checks
now require the exact fields for each of the three supported operations. Twelve
RED assertions became green; 31 focused methods pass. Existing lifecycle records,
reference outputs and generated native constants are unchanged. [Evidence](../verification/robotics-operation-record-v3.json)
records source hashes and preservation checks. This corrects fixture admission;
production telemetry, the production runtime decision and later review cursor
remain unchanged.
