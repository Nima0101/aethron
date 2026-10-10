# Supervised recorded geometry appliance — implemented increment

The `sensor-replay` driver connects the [calibrated provider](SENSOR-PROVIDER.md)
to the existing appliance worker, one-slot mailbox, watchdog, restart budget,
local status and authenticated HTTP/SSE service. It processes without viewers,
WAN, online licensing or a development terminal. This is recorded software
integration; physical-source qualification remains external. ROS clock authority
is maintained separately by the robotics lane. Raw geometry does not create
semantic detections or current live support.

## Provisioning contract

Administrator-local configuration version 1 gains one driver and one optional
field. `sensor_manifest` is required for `sensor-replay`, forbidden on existing
drivers. A raw replay profile forbids `model`: model admission needs its own
modality-specific evaluation and integration. Both paths resolve relative to the
appliance configuration. No HTTP endpoint accepts paths or changes provisioning.

```json
{
  "name": "depth",
  "driver": "sensor-replay",
  "address": "depth.aeraw",
  "sensor_manifest": "sensor.json",
  "contract": "warn",
  "lighting": "zero_visible"
}
```

`aethron_edge.sensors.provisioning.load_manifest(Path(...))` reads a closed,
strict, frozen manifest, at most 65,536 bytes. Version 1 contains exactly:

| Field | Meaning |
|---|---|
| `version` | Integer 1, never a boolean |
| `mode` | `recorded`; no host/live clock grant |
| `calibration` | Full `ProviderCalibration` including source, format SHA-256, rigid rig, source intrinsics, optional lens and declared errors |
| `indices` | 1–64 unique depth `[column,row]` pairs or valid-cloud tuple indices; bounded by the provisioned camera or 4096-point cloud limit |
| `valid_for_ns` | Explicit positive binding duration ≤600 seconds in recording time; insufficient duration rejects the recording |
| `loop` | Boolean, default false; repeated playback remains recorded |
| `recording_sha256` | Exact input SHA-256, checked before processing each cycle |

Unknown fields, duplicate JSON keys, nonfinite values, wrong types, wrong
modalities, changed calibration/format, missing files and incompatible geometry
fail closed. A complete [synthetic example](../../../examples/sensors/recorded-depth/README.md)
contains binary frames, manifest and appliance profile. No sample is a physical
calibration or zero-visible performance claim.

## Signed installed operation

Use the existing [appliance installation](../../usage-appliance.md). The offline
Ed25519 bundle must contain the actual configuration, sensor manifest and raw
recording; `verify_configuration` rejects any input outside or missing from its
signed file inventory. Runtime/model rights and immutable administrator-owned
bundle storage remain installation requirements. Signature verification occurs
at startup; an administrator able to rewrite trusted runtime files is outside
the unprivileged remote-client boundary. Using one descriptor does not snapshot
file contents against in-place writes; immutable trusted storage is required
through validation and playback. The worker additionally checks the
provisioned recording digest every cycle. Keep logs, status, credentials and
private signing keys outside the signed bundle. No private signing key ships
with the application.

The normal installed entry point is unchanged:

```sh
aethron-edge run --config /opt/aethron/appliance.json
```

The existing service manager invokes it at boot. No interactive viewer starts
or owns the worker. A one-pass recording enters `ended` and remains a bounded
idle process; it does not trigger endless watchdog restarts. Explicit `loop:true`
opens and verifies a fresh cycle after a 50 ms minimum pause. Missing/corrupt
input exits the worker with a fixed fault; the existing five-restarts-per-minute
budget applies. Reprovision/restart follows the existing local maintenance flow.

## Bounds, clocks and output

Inputs must be regular files, not device nodes, pipes or symlinks. Opening uses
nonblocking/no-follow flags where the OS provides them and checks the descriptor.
A recording is at most 64 MiB, 300 frames and 30 seconds. Hashing streams in
64 KiB chunks; playback retains one pending validated record (at most 8 MiB payload)
and at most 64 projected samples. Parser/copy and next-record handoff buffers
add bounded overhead; 8 MiB is a payload limit, not a measured process RSS cap. Entire input validation precedes processing;
it checks every record through provider admission on the same descriptor used
for playback. Long recorded gaps use cancellable ≤100 ms waits/heartbeats.
The supervisor owns termination of blocked or corrupt workers. The worker
itself checks cancellation cooperatively; hashing, validation, file I/O and the
diagnostic send callback have no local deadline. A wait interval is not a bound
on shutdown latency. If the diagnostic sink fails, final fault delivery is not
guaranteed. No hard-real-time or physical power/memory guarantee follows.

Recorded acquisition plus declared uncertainty defines the logical replay
clock. Host elapsed processing time consumes that sample's freshness budget.
Recorded timestamps never become host capture timestamps and never enter the
semantic core. Looping creates a fresh recorded provider and scene boundary;
it cannot renew live calibration. A separate host-monotonic deadline expires
only the processing diagnostic. Parent-side expiry works without incoming
messages. Loss/recovery/shutdown clears availability.

Local status adds a bounded `sensors` map keyed by provisioned profile (maximum
four), each containing `state`, cumulative `batches`, `available`,
`source_evidence:"recorded"`, and `qualified:false`. States are `idle`,
`processing`, `waiting`, `stale`, `ended`, `fault`. `available` describes a
recent recorded geometry computation, not a currently occupied/free scene.
`last_processing_ms` measures provider processing, including initial binding creation, on the host monotonic
clock, excluding file validation/pacing; it is not exposure-to-output latency.
Counters carry across supervised restarts; abrupt death can lose unpublished
increments. A batch can have zero valid selected samples; its diagnostic is
unavailable. `processed` includes worker heartbeats; `inferences` stays zero.
Status contains no point coordinates, raw bytes, source paths or calibration.

Public capabilities identify `recorded_geometry`. HTTP/SSE snapshots remain
`UNKNOWN`, empty tracks and zero live lease; connecting or disconnecting clients
does not change processing. The initial SSE gap remains part of the API contract.

## Evidence and remaining execution

Tests exercise strict provisioning, signed inventory coverage, real spawned
supervision with zero viewers, source removal, worker crash/recovery, expiry,
EOF, corrupt/oversized recordings, long-gap heartbeats, and a real signed CLI
with authenticated external HTTP/SSE clients. Packaging runs these against the
installed wheels outside the checkout. Existing core, raw provider, DDS and
negative aircraft/latency evidence remains applicable within its recorded scope.

This increment does not claim that the new driver has completed a VM boot soak.
The earlier Phase 1 VM boot/one-hour soak used its own synthetic semantic source.
ROS/DDS integration and per-boot authority belong to the separate robotics lane;
this recorded-source evidence does not qualify those interfaces. Combined Linux
autostart/offline/reboot/soak and separately evaluated nonvisible models require
their own current evidence. Models, licensed real sensor
recordings, calibration/clock hardware tuples, physical power/thermal behavior,
field safety, certification and publication gates remain pending. See [NEXT](NEXT.md).
