# Offline raw cloud inspection v1

Inspect selected packet ordinals from a local radar/LiDAR recording without ROS,
sensor activation or geometry registration:

```sh
python -m aethron_edge.sensors.cloud_inspect \
  --recording cloud.aeraw \
  --expected-recording-sha256 "$EXPECTED_RECORDING_SHA256" \
  --index 0 --index 4 --max-frames 10
```

Obtain the expected digest independently from trusted recording provenance.
The command hashes exactly the bytes it consumes, verifies each packet checksum,
and emits one JSON document only after the entire input succeeds. Digest agreement
establishes byte integrity, not publisher authenticity or physical calibration.
Errors return exit 2, empty stdout, and `invalid_cloud_inspection` on stderr.
Argument errors use the same fixed message without echoing paths or supplied text.

The library entry point is
`inspect_recording(path, expected_sha256=..., indices=(0, 4), max_frames=10)`.
It raises a fixed `ValueError` on invalid input. Bounds are 64 MiB of input,
1–64 distinct integer ordinals in 0–4095, and 1–300 frames within 30 seconds.
The default frame limit is one. Extra frames reject the input rather than truncate
the report. Empty files, directories, final-component symlinks and special files
are rejected. A stream byte counter also rejects growth past the file-size limit.
Use a trusted parent directory; this is not a filesystem sandbox.

Each report retains the validated source header, total and invalid sample counts,
and selected samples in requested order. A missing or nonfinite sample is JSON
`null`; `sample_count` distinguishes out-of-range ordinals from invalid samples.
Finite samples contain raw `xyz_m` and optional signed `radial_velocity_mps`.
These are declared source units, without a physical accuracy/range claim.
Ordinals select positions within a packet and are never object IDs or cross-frame
correspondence. Only selected values and headers are retained between records.

Reports always carry `source_evidence="recorded"`, `live_evidence=false`,
`registered=false` and `state="UNKNOWN"`. Acquisition clocks, uncertainty, source
coordinate frame and calibration digest remain source metadata. Inspection never
rebases time, validates a calibration artifact, infers a class, creates a track,
or treats an empty cloud as free space. Both fixed-layout v1 and opt-in
[variable-count v2 recordings](CLOUD-REPLAY-V2.md) are accepted. Images are rejected.

## Technology decision and evidence

Constraints: installed base-edge use on existing supported hosts, no ROS runtime
or native array dependency, bounded file reads and output, stable invalid-sample
ordinals, and no live or calibration authority. Primary sources checked on
2026-10-09:

- [Pinned upstream sensor_msgs_py implementation](https://github.com/ros2/common_interfaces/blob/a941f14bb318d8d904505ed935ccbb97f24a70a4/sensor_msgs_py/sensor_msgs_py/point_cloud2.py)
  uses generated ROS messages and NumPy, with optional NaN filtering. That general
  SDK utility adds dependencies unnecessary for this restricted offline format.
  The raw upstream source was retrieved; no implementation was copied.
- [Python hashlib documentation](https://docs.python.org/3.13/library/hashlib.html)
  specifies incremental `update` semantics. Its `file_digest` helper may bypass
  wrapper I/O, so this command hashes each bounded parser read explicitly.

Selected: reuse the strict AETHRON decoder and replay validator, with standard
Python CLI/JSON/SHA-256 support. No new package, SDK or toolchain is installed.
The shared offline helpers live in `sensors.recording_io`; `provisioning` retains
its existing imports for compatibility. A subprocess regression prevents the
inspector from importing acquisition, provider or geometry runtimes. This boundary
was introduced after a startup probe observed unnecessary acquisition imports;
it does not establish a startup latency guarantee.
`test_sensor_cloud_inspect.py` exercises actual binary fixtures and CLI processes;
the package and ROS candidate harnesses include it. This is software-only
inspection, with no latency, DDS execution or hardware qualification claim.

[Execution evidence](evidence/phase2/cloud-inspection.json) retains the earlier
30-second CLI timeout alongside passing runs, plus an installed signed-radar
deadline failure reproduced with the pre-refactor wheel. The prior [T10 failure](evidence/phase2/cloud-replay-v2-temporal.json)
also remains open. This is a review candidate for hosted validation; passing
focused software checks does not authorize merge, release or production claims.
