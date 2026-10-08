# Phase 1 implementation review

Single-author review on 2026-10-08. The owner prohibited delegation; this is not independent assurance. The acceptance record, when present, identifies the tested source and artifacts. [TEST-EVIDENCE](TEST-EVIDENCE.md) separates installation, software integration, hardware and field claims.

| Boundary reviewed | Implemented behavior / evidence | Remaining limit |
|---|---|---|
| Frozen engine and governance | Edge package is separate; original input bounds, model/data freezes and negative aircraft evidence remain. Repository verification passes. | Existing aircraft performance is inadequate; this candidate does not qualify the model. |
| Capture and time | Real isolated OpenCV file/UVC/RTSP drivers, explicit backend, single raw frame slot, receive versus exposure provenance; 100/101 ms and 50/51 ms boundary tests. | Generic capture lacks qualified exposure timestamps. Actual decoding/inference therefore produces UNKNOWN current evidence. UVC uses a virtual backend in tests. |
| Pixel processing | Licensed recording and local RTSP reach the pinned model; explicit offline pixel replay reaches registration and frozen core without ground-truth detections as input. | Replay clocks and synthetic multimodal proposals are software evidence, not measured nonvisible sensors. |
| Process ownership | Supervisor owns processing independently of clients. Bounded mailbox and stop token survive killed workers; descendant cleanup regression passes. | Native Windows job-object implementation awaits Windows execution. Some earlier shutdowns emitted a multiprocessing semaphore warning, retained in local logs. No zero-leak guarantee. |
| Client freshness | Server checks monotonic expiry; Python and TypeScript clients withdraw current state on stale/disconnected delivery. | No qualified transit clock: clients show delayed observations and current UNKNOWN. Browser/remote TLS deployment remains unqualified. |
| Local API | Token scope/ownership, Host/Origin, closed schemas, bounded bodies/sessions/subscribers, sanitized errors, no source-URI or command HTTP endpoint. | Loopback administration is the supported candidate boundary. Independent penetration/native-code review remains pending. |
| Updates | Signed complete bundle, copied-byte verification, inactive staging, atomic active pointer and version floor; real selected version-2 exec. Service cannot rename root-owned update store under root-owned parent. | Root/OS compromise, secure boot and hardware-backed anti-rollback are not covered. Release signing/key operations are not authorized. |
| Resource handling | Bounded frame/mailbox/event slots; systemd cgroup and log limits; independent worker recovery; stale evidence is withdrawn. | Native codecs may allocate before dimension rejection. Software scheduling/storage are not hard real time; status fsync can delay availability. |
| Distribution | Reproducible wheels, external installed consumers, actual Linux arm64/amd64 containers, clean-clone quickstart/source artifacts, SBOM and locked dependency audit. | Hosted workflow and unexecuted native matrix cells remain pending. OS image reproducibility is inventory/hash provenance, not byte-identical OS builds. |
| Appliance | Dedicated-account systemd image, verified boot artifacts, no guest NIC/login/provisioner, boot/reboot, worker failure, offline update and local status. | Final hour gate is recorded separately; no physical power/thermal/indicator/OEM qualification follows from a VM. |

## Review corrections retained

The VM exposed a partial multiprocessing Queue read after SIGKILL, then a condition-variable deadlock during cleanup. Both counterexamples remain in the negative ledger. The replacement is a bounded nonblocking shared-memory mailbox and one-way stop byte. A later worker-tree review added exact descendant ownership/cleanup.

A permission counterexample showed that a root-owned update directory under service-writable `/var/lib/aethron` could still be renamed. The store now lives at `/var/lib/aethron-updates`, outside service write paths; the native Linux denial test also verified that authorized version-2 execution still works.

A core integration review found that invoking the unconditional core watchdog on every API read withdrew valid step results immediately. The edge now retains only the exact last result within frozen expiry and then calls the watchdog. Neither evidence age nor model thresholds changed.

## Explicit operational limits

The internal worker message includes a JSON wrapper and uses a bounded 65536-byte mailbox. Its usable proposal payload is smaller than the frozen public wire maximum; oversized internal messages fail closed. Raw replay/API wire admission retains the frozen limit. This admission restriction is not a change to the core protocol.

The one-hour guest uses synthetic proposals. Its latency is synthetic proposal timestamp to parent processing, sampled through the aggregate status file; it is not camera exposure-to-display latency. Status-unavailable/expired samples are reported. Physical acquisition drops are inapplicable to that source; generic capture has sequence-gap counters, while long-run hardware capture/drop measurement remains pending. Appliance status exports capture sequence gaps, mailbox overwrites and busy-mailbox rejections. The soak accumulates observed deltas across service restarts. A process killed before publishing its final capture count can leave unobserved gaps; no zero-drop guarantee follows from these diagnostic counters.

No code, cache, process or communication belonging to the separate native iOS session was used. The untracked owner autonomy note is preserved separately; direct Phase 1 authorization remains the scope. No push, publication, deployment or Phase 2 work is performed.
