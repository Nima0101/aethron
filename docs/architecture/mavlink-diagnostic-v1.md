# Receive-only MAVLink diagnostic v1

Decision, 2026-10-10: add a finite console observer for the versioned datagram
adapter. Requirements are Linux operation, no outbound packets or commands,
bounded execution/output, the same strict decoder policy, and no payload export.
No real-time, SITL firmware or hardware qualification is implied.

Technology research considered the official [Python dialect API](https://mavlink.io/en/mavgen_python/),
[generated C/C++ interface](https://mavlink.io/en/mavgen_cpp/index.html),
and [Rust MAVLink library](https://docs.rs/crate/mavlink/0.18.0).
A standalone native implementation could provide a smaller deployment boundary,
but would need independent policy/signing parity or an IPC bridge. This component
only projects existing versioned status into fixed aggregate records; it does
not need a new wire parser or high-throughput runtime. Choose Python with
[stdlib argparse](https://docs.python.org/3.13/library/argparse.html) and JSON,
calling the public v1 receiver. No new dependency or automatic connection helper
is introduced. Revisit native transport only with measured runtime requirements
and executable policy parity; existing language ownership is not a selection rule.

`python -m aethron_edge.telemetry.diagnostic_v1 --port PORT --duration-ms N`
accepts explicit duration 1..30000 ms and port 0..65535 (0 selects an ephemeral
loopback port). Optional `--system-id` and `--component-id` are 1..255, default1.
It receives only already configured loopback traffic. This diagnostic accepts
unsigned packets only; signed traffic is rejected by the passive decoder, never
downgraded or retried. Provisioned signed consumers use the separate library API.

Output is JSON lines: one `listening` record with the selected port, at most1500
`status` records, and one final UNKNOWN/closed status on normal completion.
Status fields are version, event, state, reason, sample_count, authenticated,
evidence, perception_eligible. There are no coordinates, angles, sender IDs,
boot times, signing secrets, packet bytes, or histories in diagnostic output.
The decoder retains at most two latest samples within its existing receipt TTL.
No input is saved. Output consumers decide whether to retain aggregate diagnostics.

The monotonic duration and 1500-poll cap independently stop admission. Socket
waits are bounded by the existing20ms timeout; process scheduling or a blocked
stdout can delay exit, so the duration is not a hard real-time wall-clock bound.
After a poll crosses the session deadline, its result is not emitted as observed.
Silence still expires observations. Bind/SDK/runtime failures use a fixed error
without exception details; normal exit and handled errors release owned sockets.
This is a software diagnostic, not a safety supervisor or actuation interface.

Acceptance uses an actual subprocess and synthetic SDK packets over localhost:
two-message observation, aggregate-only output, malformed withdrawal, timeout,
normal close, no outbound response, invalid arguments, and occupied-port failure.
