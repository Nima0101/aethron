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
