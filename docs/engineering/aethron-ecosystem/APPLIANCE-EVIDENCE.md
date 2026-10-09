# Appliance acceptance scope

Source candidate: `d90ae953f6431fd9d460e440432ac72825b8d250`. The [final guest result](evidence/phase1/boot.json) passed the real boot/reboot, worker recovery, offline update and one-hour second-boot gate. This table maps implemented software to A01–A09 without promoting simulation to hardware evidence. [PHASES](PHASES.json) remains the acceptance authority.

| Gate | Executed software path | Physical / external work still required |
|---|---|---|
| A01 provision once | Builder verifies/signs local runtime and boot artifacts; image creates restricted account and enables systemd; first boot runs without login. No build-host service installation. | Authorized device image/provisioning, permanent local key storage and commissioning per SKU |
| A02 no companion/WAN | QEMU guest has no NIC, shared guest directory, forwarded port, SSH, phone, viewer or provisioning endpoint. Fixture and runtime are local. | Remove actual provisioning cables/radios on the installed rig while preserving sensor wiring and power |
| A03 power lifecycle | Guest reboots through systemd; process-local scenes restart; inactive partial update is rejected. Startup has no restored track state. | Brownout, ignition/payload/PoE transitions, unclean-power filesystem recovery and battery drain |
| A04 sensor/night faults | Core blackout/all-loss fixtures, source disconnect/reopen, stale/unknown-clock/calibration tests; generic capture remains UNKNOWN; virtual multimodal replay distinguishes valid nonvisible support. | Real nonvisible sensor decoder/model, optics, clocks, calibration, environmental tests and zero-visible accuracy |
| A05 worker/provider faults | Guest kills an inference worker and must resume before update; integration tests cover killed writer, stalled cleanup, descendants, five/60-second restart budget and latched fault. Unsupported providers are not silently substituted. | Exact accelerator/driver crash, device reset and independent hardware watchdog behavior |
| A06 resources | One-hour second-boot harness samples synthetic processing latency, observed capture-gap/mailbox drops, cgroup memory, status availability/size and journal size. Disk-full failure test is separate. | Camera exposure-to-output latency, full acquisition drop accounting, long-duration leaks, power, temperature and declared environmental duration |
| A07 update/recovery | Ed25519/hash/complete-file/config validation, incomplete staging, signed version-2 activation/exec, rollback rejection, local reset tests. Root-owned update parent blocks service-account replacement. | Production key custody/revocation, secure boot, hardware anti-rollback and OEM/OS A/B integration |
| A08 no viewers | Guest has zero API viewers; local bounded status continues. Installed API tests close observers and require increasing processing counters. | Physical independent LED/display/audio fault indication, including total process/OS death |
| A09 class recipes | Common Linux software procedure plus [OEM](../../appliance/oem-embedded.md), [retrofit](../../appliance/vehicle-retrofit.md), [drone](../../appliance/drone-companion.md), [home hub](../../appliance/home-hub.md) operator guides | Exact OEM permissions, fixed mounting/wiring, flight/payload and camera/NVR integration. No class-specific SKU trial was performed. |

## What the guest measures

The service runs synthetic multimodal proposals through the production supervisor and frozen temporal core. Separately executed installed file/RTSP tests use licensed RGB pixels and the actual pinned model. Combining these two evidence lanes establishes software integration; it does not turn the guest into a physical sensor rig or prove perception accuracy.

`latency_ms` is the sampled synthetic proposal timestamp-to-parent-processing interval. Samples come from once-per-second local aggregate status, not every frame; p99/max are sampled values, not guaranteed worst-case bounds. `service_cgroup_peak_bytes` is the maximum observed cgroup memory, not process RSS; `rss_probe_kib` is the test probe's RSS. `drops` contains observed aggregate deltas across worker/service restarts. Capture gaps are zero/inapplicable for synthetic proposals, while actual mailbox drops are measured. Abrupt death can lose unpublished counter increments, so no zero-drop guarantee is inferred. Startup/update status-unavailable or expired samples remain in the record.

The image constrains service memory/tasks and journal growth. A limit provides containment, not evidence that all native allocations are safe or that deadline/memory qualification is complete. No physical wattage or temperature is measured. Startup and update timings are functional availability measurements; the frozen 100ms current-evidence expiry is never extended to match them.

The VM still runs on a development host and a Docker-contained QEMU process. Its guest has the independent installed lifecycle required for software-in-loop acceptance; it is not proof that a physical appliance has been installed. Local test signing keys are not release credentials. No hardware or actuator was operated.

## Measured final run

The actual second boot ran 3,600.66 seconds. Sampled synthetic processing latency: p50 8.513ms, p95 14.057ms, p99 17.034ms, max 87.603ms. Observed service cgroup peak: 123,715,584 bytes (about 118MiB); status record at most 347 bytes; journal 1,048,576 bytes. The report retains 89 mailbox overwrites, 208 busy-write rejections and 72 expired status samples; no uninterrupted-availability or zero-drop claim is made. Capture gaps are inapplicable to the synthetic source, and abrupt death can lose unpublished diagnostic increments.
