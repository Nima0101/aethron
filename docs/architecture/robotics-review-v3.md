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
