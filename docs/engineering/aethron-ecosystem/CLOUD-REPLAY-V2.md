# Recorded cloud replay amendment v2

2026-10-09. This opt-in extension changes only the raw recorded sensor header,
not frozen perception protocol v3, live ROS admission, or the v1 replay contract.
All v1 recordings still require identical layouts. Older readers reject v2.

## Constraint and technology decision

An unordered radar/LiDAR cloud can contain a different number of returns in each
packet, including zero. The v1 reader rejects these changes even though the
existing cloud calibration format digest excludes packet dimensions and padding.
The deployment needs offline installed-wheel consumption without ROS, device
access, network services or a new native dependency. Each record must remain
bounded to 16 KiB of metadata, 8 MiB of payload and 4,096 points. Provisioned
replay remains bounded to 300 frames, 30 seconds and a 64 MiB file.

Primary sources reviewed independently on 2026-10-09:

- [ROS PointCloud2 at the existing pinned revision](https://github.com/ros2/common_interfaces/blob/a941f14bb318d8d904505ed935ccbb97f24a70a4/sensor_msgs/msg/PointCloud2.msg)
  distinguishes point-field layout from packet width/height/row stride. The raw
  upstream file was retrieved; rendered ROS documentation denied access.
- [Official rosbag2](https://github.com/ros2/rosbag2) provides general ROS message
  recording/playback and storage plugins. It is useful for broader ROS capture,
  but this narrow offline reader needs neither ROS discovery nor topic playback.

Selected implementation: extend the existing Python binary reader and reuse its
strict Pydantic layout validation and semantic `layout_digest`. This avoids a
second deserializer and dependency closure. No upstream implementation is copied,
no toolchain installed, and no latency or hardware qualification is claimed.

## v2 contract

Set the raw header `version` to integer `2`; all other fields and framing stay
unchanged. v2 accepts only radar/LiDAR `CloudLayout` records. Images still use v1.
Within a v2 stream:

- Width, height and row stride may vary, subject to every existing per-packet
  layout/resource check. Empty clouds are permitted and convey no free-space claim.
- Byte order, point stride, and the complete ordered field declarations stay
  constant. Source, modality, coordinate frame and calibration digest stay constant.
- Versions cannot mix. Sequence strictly increases; acquisition time cannot rewind.
- Each payload has its own verified checksum and exact validated byte length.
  Hashes are corruption checks, not authentication.
- Invalid points retain their packet ordinal positions in `sample_points`.
  Ordinals are sample selectors within a packet, never object identifiers or
  correspondence across packets. Missing selected ordinals still cause the geometry
  provider to fail closed; this amendment does not make them valid measurements.

`read_frames` is incremental and may yield an earlier valid frame before a later
error. Provisioned playback still validates the complete digest-bound input
before using it. All frames remain recorded and `live_evidence=False`; replay
creates no live timestamp, calibration authority, semantic class or track.

## Verification

`test_sensor_cloud_replay_v2.py` exercises changing counts, empty and organized
clouds, padding, invalid sample ordinals, legacy behavior, mixed versions, changed
format/provenance, corruption and resource limits. The initial regression rejected
v2 at header validation; it is preserved by the same positive test. The installed
ROS candidate harness includes these portable tests; execution of that hosted
workflow remains a separate requirement, not evidence supplied by this document.

[Executed evidence](evidence/phase2/cloud-replay-v2.json): 23 targeted tests and
five installed-wheel tests passed; core verification passed 218 tests with five
skips. Full temporal evaluation failed frozen T10 (p95 143.527 ms > 100 ms).
The [complete report](evidence/phase2/cloud-replay-v2-temporal.json) retains the
recorded excerpt's 20 false negatives and 721 false positives. Core runtime bytes
were unchanged. Publication is held; no threshold was modified or failure waived.
