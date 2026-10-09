# Supervisor-owned ROS geometry — development checkpoint

`sensor-ros` connects the bounded ROS Image/CameraInfo/PointCloud2 subscriber and calibrated sparse geometry provider to the installed edge supervisor. It works without API viewers and produces aggregate local status. No raw points, calibration identifiers or invented semantic classes reach HTTP/SSE: the existing scene remains UNKNOWN. Installed Linux ARM64 DDS tests use synthetic bytes, not a physical sensor. Full candidate qualification is pending.

## Explicit clock authority

A signed administrator-local manifest opts into **same-host system-time software timestamps**. This supports a local software publisher; it does not discover sensor exposure time, synchronize a remote device, authenticate a DDS publisher or accept `/clock` simulation. The existing direct library API can still accept explicitly supplied mappings under its separate caller-owned contract.

At supervisor startup, the parent brackets one system-clock reading with monotonic readings. Sampling must finish within 1 ms. A random per-boot token, the exact manifest digest, declared timestamp uncertainty, measured bracket error, allowed drift and finite monotonic deadline bind the worker. The grant is private parent/worker IPC: no JSON/HTTP/DDS import endpoint, persisted monotonic timestamp or online issuer exists. A worker replacement receives the currently issued grant, its unchanged deadline and the parent revocation state. A crash never issues a new grant. Changes to the manifest cannot extend that authority.

Before and after each subscriber poll, a clock guard checks the monotonic progression, sampling interval, absolute drift relative to the original mapping and deadline. Failure permanently revokes that guard and clears pending geometry/clock/calibration. It never silently remaps an input timestamp to make it fresh. Parent status independently enforces the 100 ms processing diagnostic and the boot deadline. Existing source/frame/layout/calibration/freshness checks still apply; clock validity alone never proves physical evidence.

## Opt-in software renewal (manifest version 2)

Version 1 retains its single ≤600-second grant and no renewal. Version 2 may explicitly set `"renewal": "software_fixture"` only with `calibration.rig.evidence = "synthetic"`. The default is `"disabled"`. This is an unattended software/SIL lifecycle, not a physical calibration authority. A real installation still needs a qualified mount/exposure-clock revalidator; simply rereading its calibration file cannot prove it remains correct.

After half the current lease, the parent may issue one successor only while the old grant is valid and the worker reports fresh, nonempty, successfully registered geometry. The parent rereads and validates the bounded manifest, compares its exact canonical digest to the boot authority, and checks the unchanged original clock offset/drift/uncertainty. Each generation has a new finite deadline ≤600 seconds; drift budgets never accumulate or reset. Expired, closed, changed, stale or future evidence cannot authorize renewal. Missed renewal expires normally; no reconnect can resurrect a revoked authority within that service boot.

A bounded private parent-to-worker mailbox carries the successor. The worker independently checks the original grant is still valid, the reread manifest matches, and the successor preserves the boot token, original offset/error, exact next generation and bounded deadline. It then closes the old provider, clears pending frames and CameraInfo, starts a fresh binding/scene and reacquires matching calibration and observations. Source stamp ordering survives the epoch transition, preventing replay of old frames. Parent diagnostics become unavailable immediately at issue and ignore prior-generation messages; only new-generation fresh geometry restores availability. Lost, malformed or delayed handoffs fail closed. No HTTP/DDS grant-import or actuation interface exists.

`authority_generation` in local aggregate sensor status is a counter, not a physical qualification claim. `authority_fault` reports only a fixed category (clock sampling/drift/rewind, expiry, rejected renewal, source discontinuity/invalidity or worker fault); it never echoes exception details. A matching CameraInfo callback with no new image preserves the prior diagnostic only until its original expiry, without adding a batch or refreshing its evidence. All raw geometry remains `external_unverified`, semantic output remains UNKNOWN, and no sensor payload/history is persisted. Suspend, a clock step, budget exhaustion or expired authority requires explicit service revalidation/restart. Remote/PTP authorities, real sensor exposure timing and physical mount revalidation remain pending; this opt-in fixture path does not reduce that scope.

## Provisioning

The normal CLI remains `aethron-edge run --config /path/to/appliance.json`. The [existing signed installation procedure](../../usage-appliance.md) applies: the verified bundle must include both appliance configuration and ROS manifest. Neither HTTP clients nor ROS messages can replace them. No licence server, cloud, provisioning cable or viewer is required for local processing.

```json
{
  "name": "depth",
  "driver": "sensor-ros",
  "address": "/aethron/depth",
  "sensor_manifest": "sensor.json",
  "lighting": "zero_visible"
}
```

The [synthetic example](../../../examples/sensors/ros-depth/README.md) includes the complete version 1 manifest. It is intentionally unsigned and must not pass normal appliance CLI integrity checks until provisioned. Its declared geometry is an analytical fixture, not a calibration for a real camera.

| Manifest field | Admission |
|---|---|
| `version`, `mode` | Integer 1/2 (undistorted depth/cloud) or 3 (explicit raw depth), and `ros` |
| `image_geometry` | Required `raw_distorted` in version 3; forbidden in older manifests |
| `renewal` | Default `disabled`; `software_fixture` requires version 2/3 and synthetic rig evidence |
| `timestamp_authority` | Exactly `same_host_system_software`; no implicit mode |
| `calibration` | Full provider calibration, layout digest, source/mount/frame and declared errors |
| `indices` | 1–64 unique camera pixels or bounded cloud indices |
| `valid_for_ns` | Positive ≤600,000,000,000; relative duration, not stored host epoch |
| `timestamp_error_ns`, `clock_drift_budget_ns` | Each 0–49 ms; total plus 1 ms sample envelope ≤50 ms |
| `topic`, `camera_info_topic` | Absolute, validated, distinct; camera-info required for depth and null for radar/LiDAR |
| `domain_id` | Integer 0–232 |
| `meters_per_unit` | Positive ≤1 for depth, null for clouds; actual layout hash must also match |

Versions 1/2 retain zero-distortion CameraInfo admission and unchanged serialized digests. Version 3 requires a provisioned Brown or fisheye lens, depth modality and explicit raw-stream selection. The worker matches model/D/K/P/frame/dimensions before sparse correction; it refuses double correction, changed metadata and expired leases. A renewed CameraInfo lease cannot extend an old queued image. See the [raw fixture](../../../examples/sensors/ros-raw-depth/README.md), [lens contract](SENSOR-REGISTRATION.md) and [development evidence](evidence/phase2/raw-depth-provisioning.json). This does not add raster remapping, stereo, a semantic model or new physical clock authority. The profile-level `model` field remains rejected on this driver. JSON types are strict, duplicate/unknown fields fail and input is bounded to 65,536 bytes. Final manifest symlinks are rejected.

The worker requests localhost-only DDS discovery and constructs its own context/node/executor without command publishers, global ROS arguments or parameter services. Administrators must also isolate DDS traffic and configure publisher permissions: discovery settings are not authentication or a network firewall. Only the pinned offline Jazzy image tuple has installed execution evidence; other middleware/SDK distributions remain unqualified. Missing `rclpy` becomes a fixed fault and existing bounded supervisor recovery, never a hidden download or fallback success.

## Verification and next integration

Focused tests cover manifest boundaries, wrong boot/digest, stale grants, immutable restart deadlines, drift/rewind, optional SDK absence, signed-input inventory and parent expiry. The installed DDS test exercises real synthetic publishing through the child worker/supervisor, zero viewers, loss, crash/recovery and manifest-change rejection. Resource limits are inherited from the pinned unprivileged, network-disabled container. New code is GPL-3.0-only; upstream ROS and package licences remain separate.

Next: qualify the accumulated raw/ROS renewal changes through installed consumers, boot/offline/reboot/soak and the affected full candidate lanes; integrate separate physical/remote clock and calibration authorities when their actual evidence permits. Preserve all Mac startup/availability failures. Neither these checks nor a `zero_visible` label establish zero-light sensor performance.

Clock semantics were checked on 2026-10-09 against [ROS clock design](https://design.ros2.org/articles/clock_and_time.html) and [Python time documentation](https://docs.python.org/3/library/time.html). ROS system, ROS simulation and steady clocks are distinct; local bracketing here is an implementation assumption for declared same-host software stamps. Existing execution pins: Jazzy rclpy 7.1.12, sensor_msgs 5.3.8, rmw_fastrtps_cpp 8.4.4; see the [ROS integration evidence](evidence/phase2/ros2.json). No upstream document certifies this implementation.

The [signed CLI evidence](evidence/phase2/ros-cli.json) now exercises this exact installed runtime through normal integrity-verifying startup, original synthetic DDS publishing, authenticated external HTTP/SSE and continued processing after viewer removal. Missing server dependencies were reproduced and repaired in the ROS harness closure; final installed lane passed 72 tests. That historical result closes the named software-consumer gap at its recorded source, not current renewal, boot/soak, Mac availability or physical qualification. The [renewal checkpoint](evidence/phase2/ros-renewal.json) records the new runtime, final passing installed run and unresolved intermittent failures separately.


The [availability checkpoint](evidence/phase2/availability-revocation.json) captured a real software-clock offset shift beyond the configured bound. Revocation now latches the supervisor fault immediately and triggers asynchronous worker cleanup without crash-restart attempts; the sensor keeps its fixed fault code after cleanup. Healthy pre-expiry worker crash recovery remains tested separately. Operator/service revalidation is required after revocation; reconnecting a publisher or restoring wall time cannot revive the old authority. This is deliberate withdrawal, not a continuous-operation qualification.
