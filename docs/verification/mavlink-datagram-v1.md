# MAVLink datagram v1 focused verification

2026-10-09; base revision `2d29c3b852936fac9cddf66a55040d1b9a816179`.
Software-only lane increment; no ROS/P2 internals changed.

Historical pre-migration CPython 3.13.15/macOS ARM64, using the existing hash-locked pymavlink 2.4.50,
fastcrc 0.5.0 and lxml 6.1.3 SDK. Source tests use
`PYTHONPATH=integrations/edge:tests/mavlink`.

| Focused check | Result |
| --- | --- |
| `python -m unittest test_datagram_v1 test_telemetry -v` | 26 PASS, 4.919 s |
| Six existing `test_signing.SigningTests` cases below | 6 PASS, 6.788 s |
| Ruff 0.16.10 check and format check, new adapter/test file | PASS |
| Bandit 1.9.4, new adapter | PASS, no findings |

Linux continuation, 2026-10-09: CPython 3.13.5/x86_64. Installed the same three
SDK versions using the new Linux CPython 3.13 wheel lock with `--only-binary=:all:`
and `--require-hashes`. Ran the 26 adapter/passive cases and six signing cases
together: **32 PASS in 0.304 s**. Scoped Ruff check/format and Bandit passed;
the Linux workflow YAML parsed successfully. CI targets Ubuntu 24.04/CPython
3.13.15; that hosted Python patch version has not been verified by this local run.
No Mac execution was performed during the Linux continuation.

Selected signing cases: `test_signature_authentication_does_not_upgrade_measurement_evidence`,
`test_replay_rejected_after_restart_and_across_simultaneous_receivers`,
`test_signature_tampering_unsigned_downgrade_and_other_link_are_rejected`,
`test_expiry_withdraws_without_traffic_and_cannot_recover`,
`test_clock_rollback_and_not_yet_valid_authority`, and
`test_forged_higher_timestamp_cannot_poison_replay_state`.

Retained counterexamples, all now covered by passing regressions:

- Initial test-first run: ten assertions failed because the versioned adapter
  did not exist. Implementation then passed those ten cases.
- `test_new_batch_cannot_extend_previous_batch_receipt_deadline`: an ATTITUDE
  sample decoded after a delay remained visible after its original datagram
  receipt deadline when a newer position batch arrived. V1 now replaces previous
  samples before decoding each fully framed batch; replay counters survive.
- `test_rejection_reason_survives_silence`: an unsupported-message rejection
  became `datagram_expired` after silence. Rejected batches now discard their
  receipt deadline while preserving the decoder's failure reason.
- Workflow YAML parsing initially rejected the unquoted `--only-binary=:all:`
  command scalar. The command now uses a YAML block scalar.

Tests exercise real SDK wire encoding/decoding, synthetic public signing keys,
temporary replay journals and localhost sockets. The bounded byte cases are
focused regression coverage, not a full fuzz campaign. No command or actuation
output, vehicle connection or perception eligibility is introduced.

Full repository verification, installed packaging, clean clone, artifact
reproduction, full fuzz, ROS/DDS execution and actual PX4/ArduPilot SITL were not
run in this fast loop. The added focused workflow has no hosted result yet.
Prior timing/aircraft/availability negatives remain unchanged. This checkpoint
does not qualify hardware, physical freshness, firmware tuples or production.

## Linux snapshot-boundary continuation — 2026-10-10

Retained RED: two new test methods produced four assertion failures on the prior
adapter. A real SDK-decoded sample returned `OBSERVED_UNVERIFIED` after snapshot
processing advanced the injected clock beyond 100 ms. Snapshot-time rollback,
boolean clock and missing clock each also returned an observation before the
wrapper could detect the fault. These fixtures change only elapsed time around
the real decoder's public snapshot; they do not substitute fabricated samples.

The wrapper now checks time again after the decoder returns. The exact 100 ms
boundary remains accepted; 100 ms plus 1 ns withdraws the batch. A subsequent
fresh batch may recover ordinary expiry, but clock failure stays latched closed.
A slow unsupported-message rejection retains its original reason.

Focused CPython 3.13.5 Linux results: 33 adapter/passive/diagnostic tests passed
before adding the slow-rejection regression; the final 18 adapter cases then
passed. Six selected signing cases listed above also passed. Thus all 40 distinct
focused cases passed across these runs. Ruff lint/format and scoped Bandit pass.
No local Docker, simulator, full suite or full fuzz was run. Local RED/GREEN logs
are retained in the lane's ignored `build/p31-linux/` directory.

Earlier delivered head `f944f8f717e157c06718604d5c5fe4616cb0e53d` passed hosted
[passive wire](https://github.com/Nima0101/aethron/actions/runs/37999711110/job/114054527608)
and [offline DDS](https://github.com/Nima0101/aethron/actions/runs/37999711141/job/114054527727).
Other checks were still queued/running at the continuation snapshot. Those
results do not qualify this repair or later heads; no all-checks-green or merge
claim is made.
