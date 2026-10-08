# P2.1 sensor packet and replay implementation

This checkpoint implements raw sensor decoding and replay inside the installed `aethron_edge.sensors` package. It is partial P2.1. The optional ROS Jazzy node now runs against installed wheels and real DDS; vendor-specific acquisition, nonvisible semantic models, qualified clock mapping and physical calibration remain pending. Nothing here promotes synthetic or recorded input into current live support.

## Implemented contract

- `packets.decode_image(layout, bytes)`: LWIR/NIR `mono8`/`mono16` counts; depth `16UC1` with explicit metres-per-unit or `32FC1` metres. Endianness and row padding are respected. No thermal temperature conversion or inferred depth from intensity. Zero, negative, nonfinite or depth over the existing 500m software envelope yields unknown depth, never free space.
- `packets.decode_cloud(layout, bytes)`: scalar FLOAT32/FLOAT64 x/y/z, optional signed radial velocity, with point/row padding and either byte order. Nonfinite points are discarded with an explicit count. Unknown/overlapping fields, identity metadata and malformed buffers are rejected. This is a deliberate subset of PointCloud2, not a generic ROS deserializer or vendor UART parser. It does not infer object classes, image boxes or IDs.
- `geometry.Pinhole`: rectified optical projection/deprojection, x right/y down/z forward; axial depth is distinct from Euclidean range. Distorted inputs must first be rectified with a separately verified calibration. Finite geometry and image bounds are checked; extreme integer/malformed inputs fail closed. No camera-to-radar extrinsic is invented.
- `replay.read_frames(binary_stream)`: incremental raw records, each with a four-byte big-endian header length, UTF-8 JSON header and layout-sized payload. Header at most 16KiB, payload at most 8MiB, images at most 1920×1080 and clouds at most 4096 points. Exact SHA-256 detects payload corruption, not authenticity. No implicit file/network access or device activation occurs.

Replay headers require `version: 1`, source ID, sequence, acquisition nanoseconds, `clock_domain: "recorded_monotonic"`, uncertainty, coordinate frame, modality, optional calibration SHA-256, payload SHA-256 and layout. Source, modality, frame, calibration and layout must stay constant within a stream; start a new stream after a configuration change. Sequence must increase; clock may stay equal but cannot go backwards. Closed schemas reject unknown/identity fields and duplicate JSON keys. Truncation, oversize and corruption raise errors. Reads are size-bounded and tolerate short reads; a caller supplying a blocking network stream must enforce its own transport deadline. The intended source here is a local binary recording.

Every `RecordedFrame.live_evidence` is false. The existing trusted live-clock/calibration admission is not bypassed. Acquisition time is recorded provenance, not a new host timestamp. A calibration digest names an artifact and does not prove its physical validity. Future semantic output must independently satisfy frozen v3 timing, registration, class/model and uncertainty requirements.

## Installed Python example

```python
from aethron_edge.sensors.packets import decode_image
from aethron_edge.sensors.geometry import Pinhole

layout = dict(modality="depth", encoding="16UC1", width=2, height=1,
              step=4, is_bigendian=False, meters_per_unit=0.002)
frame = decode_image(layout, b"\x00\x00\xc4\x09")  # synthetic 0 and 2500 counts
assert frame.depth_m(0, 0) is None
assert frame.depth_m(1, 0) == 5.0
camera = Pinhole(width=2, height=1, fx=2.0, fy=2.0, cx=0.0, cy=0.0)
assert camera.deproject(1.0, 0.0, 5.0) == (2.5, 0.0, 5.0)
```

Tests exercise byte order, padding, depth scale, nonfinite points/depth, organized FLOAT64 clouds, empty clouds, malformed/huge inputs, prohibited metadata, projection/range, checksum/truncation, short reads, duplicate JSON keys, recorded clock ordering and calibration changes. Installed-consumer checks copy these tests outside the checkout and run against built wheels with Python isolated mode. All fixtures are original synthetic bytes; no third-party night dataset or sensor recording was obtained in this checkpoint. Resource bounds are software bounds, not a measured physical sensing range or performance guarantee.

## Primary source provenance — retrieved 2026-10-08

| Source | Decision and limit |
|---|---|
| [Linux 6.12 V4L2 luma formats](https://docs.kernel.org/6.12/userspace-api/media/v4l/pixfmt-yuv-luma.html) | Explicit Y16 little/big-endian handling; a 16-bit container does not establish actual ADC precision or radiometric temperature. Direct V4L2 acquisition remains future adapter work. |
| [ROS common_interfaces pinned revision](https://github.com/ros2/common_interfaces/tree/a941f14bb318d8d904505ed935ccbb97f24a70a4/sensor_msgs) | Jazzy branch resolved to `a941f14bb318d8d904505ed935ccbb97f24a70a4`; package manifest says `sensor_msgs` 5.3.8, Apache-2.0. Image, PointCloud2 and PointField layouts informed original GPL-3.0-only AETHRON code. No SDK/message implementation is bundled. Exact file hashes/URLs are in [source evidence](evidence/phase2/ros-provenance.json). ROS documentation pages presented an access challenge; the official pinned source was read instead. |
| [RealSense projection documentation](https://dev.realsenseai.com/docs/projection-in-realsense-sdk-2-0/) | Z16 needs device depth scale and zero is invalid; optical-frame pinhole math is implemented only for rectified data. No RealSense SDK is installed and no sensor SKU is qualified. Documentation retrieval is not an SDK version pin. |
| [TI mmWave-L SDK 05.05.00.02 demo output](https://software-dl.ti.com/ra-processors/esd/MMWAVE-L-SDK/05_05_00_02/exports/api_guide_xwrL64xx/MMWAVE_DEMO.html) | Documentation's header-size prose and displayed C fields appeared inconsistent. Do not guess a firmware-specific UART parser. The explicit point-cloud subset is the first interchange boundary; pin actual firmware headers, terms and captured packets before claiming TI adapter support. No SDK archive is redistributed. |

## Next implementation and qualification

The [installed ROS bridge](../../../integrations/edge/ros2/README.md) implements Image/CameraInfo/PointCloud2 subscriptions, explicit clock mapping, pending-frame bounds, calibration invalidation, loss handling and headless status. Its actual Jazzy/DDS software tuple and retained failures are in [ROS evidence](evidence/phase2/ros2.json). The initial CameraInfo contract accepts only zero-distortion monocular identity rectification. Implement validated distortion/rig registration and supervisor/model-provider integration next. Then connect licensed nonvisible pixels/packets to evaluated modality-specific models; raw radar points do not themselves establish pedestrian or UAV classes. Physical acquisition/clock, optics, scale, extrinsics, darkness/weather, power, thermal and SKU/firmware gates stay pending until measured.

ROS provenance: [pinned SDK source records](evidence/phase2/ros2-provenance.json), [ROS clock design](https://design.ros2.org/articles/clock_and_time.html), and [official runner matrix](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) were read on 2026-10-08. ROS time may pause/jump; host receipt is not exposure time. The new ARM64 workflow is prepared, not remotely executed.
