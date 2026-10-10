# AETHRON edge

Local installable integration candidate around the frozen AETHRON core. Community code is GPL-3.0-only; separately negotiated commercial terms are controlled by the project owner. Optional models, datasets, codecs and SDKs retain their own licenses.

The installed appliance owns capture and processing independently of viewers, phones, laptops and WAN. Python/CLI/HTTP tools support commissioning and maintenance. Generic file/UVC/RTSP capture runs through isolated workers; unknown exposure timing cannot become fresh v3 evidence. Replay is explicitly virtual. No actuation or field-safety qualification is included.

See the repository's `docs/usage-edge.md`, `docs/usage-appliance.md` and source-bound Phase 1 evidence before making compatibility claims. Runtime does not fetch models or contact an online licensing service.

The `sensor-replay` profile now runs calibrated raw recordings in the independent appliance supervisor. See [provisioning, bounds and evidence](../../docs/engineering/aethron-ecosystem/SENSOR-APPLIANCE.md). This is recorded geometry with no semantic detections or qualified live source.

Raw radar/LiDAR sample indices refer to original row-major packet positions, including invalid points across organized rows; row padding does not consume an index. Selecting an invalid point yields no geometry; it never selects the next valid point. `Cloud.points` retains the finite-points view, while `Cloud.sample_points` preserves packet slots with `None` for invalid samples. Recorded replay stays recorded and unqualified, including when its configuration and bytes are signed.

The `doctor` and `replay` configuration file must be UTF-8 JSON, at most 65536
bytes and eight nesting levels, with unique object keys and integer `version: 1`.
Replay requires a nonempty UTF-8 path without NUL; paths resolve relative to the
configuration. Invalid configuration emits only `invalid_request` and no report.
These are local configuration admission bounds, not new sensor thresholds.

The JSONL replay CLI consumes bounded lines instead of loading the entire recording.
`aethron_edge.protocol.replay_stream(binary_stream)` returns a complete `ReplayReport`
only after all input passes the existing 300-frame, 30-second and 65536-byte line bounds;
the caller closes the stream. Malformed trailing data produces no partial CLI report.
With the packages installed, `python scripts/edge_replay_profile.py --samples 1`
compares input allocation and report parity against whole-file ingestion.
[Measured input-allocation evidence](evidence/p11-replay-input.json) is synthetic;
the retrospective P1.1 runtime comparison remains incomplete.

An optional native exposure-clock wheel compiles the same `timebase.py` using
Cython 3.3.0. From the repository root, install the pinned build dependencies,
then explicitly select the native build:

```sh
python -m pip install setuptools==84.0.0 wheel==0.48.0
python -m pip install --no-deps --require-hashes -r requirements-native.lock
AETHRON_BUILD_NATIVE_CLOCK=1 python -m pip wheel --no-deps --no-build-isolation -w build/native-clock-wheels ./integrations/edge
```

On PowerShell, set `$env:AETHRON_BUILD_NATIVE_CLOCK='1'` before the wheel command.
Without this selection, the wheel is portable Python; runtime never compiles or
downloads a backend. Native wheels require a matching OS, architecture and Python
ABI. After installing the wheel and its dependencies, run
`python -I scripts/edge_capture_clock_profile.py --require-native` to verify the
loaded extension against its packaged Python reference. Clock integers remain
arbitrary precision. Native compilation does not establish exposure trust, change
expiry bounds or qualify live capture; the live source still fails closed when
its clock is untrusted.

Fleet health has a local, bounded library interface:

```python
import time
from aethron_edge.runtime.fleet_health import FleetHealth, encode_local_health

health = FleetHealth(slot_count=1)  # Keep this collector across samples.
now_ms = time.monotonic_ns() // 1_000_000
# supervisor is the application's existing ApplianceSupervisor.
raw = encode_local_health(supervisor.status(now_ms * 1_000_000), now_ms=now_ms)
health.ingest(0, raw, now_ms=now_ms)
counts = health.snapshot(now_ms=now_ms)
```

Output contains only runtime state counts, always `scene_state: UNKNOWN` and
`qualified: false`. Reports expire within 2000ms; malformed or replayed reports
withdraw the affected slot. Use only one trusted local monotonic clock domain:
remote device boot clocks cannot be compared directly. Slot authorization,
authenticated collection and cross-host clock mapping remain integration work.
See the [versioned contract and technology decision](../../docs/architecture/fleet-health-v1.md).
