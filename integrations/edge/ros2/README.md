# AETHRON optional ROS 2 sensor ingress

This installed edge module receives ROS `Image`, `CameraInfo` and `PointCloud2` messages. It decodes original sensor samples and reports expiring local status without a viewer or WAN. It does not yet connect a nonvisible semantic model to the appliance's perception pipeline. Raw observations always carry `live_evidence=False`; status remains `UNKNOWN`.

The executed software tuple is Linux ARM64, ROS Jazzy, Python 3.12.3, rclpy 7.1.12, sensor_msgs 5.3.8 and rmw_fastrtps_cpp 8.4.4. Other middleware versions, x86, vendor drivers and physical devices remain unqualified. The test image is pinned by platform manifest:

```
ros@sha256:8f687fdf084482819aa7dab48c3887331edd0d3687b219951fdb66c418316ab1
```

## Installation and use

Provision an authorized ROS Jazzy host with its sensor driver. Source its ROS environment and install the built AETHRON core and edge wheels into a Python environment that can import the distribution's `rclpy` and `sensor_msgs`. ROS is deliberately not fetched as an implicit pip dependency. For the tested image, the offline installation procedure is executable in [container_check.py](container_check.py), using the hash-locked [dependencies](requirements.lock). These are local candidate wheels, not a claim of published PyPI versions.

An example depth sidecar, after installation:

```sh
python -m aethron_edge.sensors.ros2_node \
  --modality depth --topic /front/depth/image \
  --camera-info-topic /front/depth/camera_info \
  --frame-id front_optical --meters-per-unit 0.001 --domain-id 42
```

Use the actual sensor scale, frame ID and topic; 0.001 is an example, not a device default. The process runs until terminated and handles SIGTERM cleanly. It emits pixel-free status records with host-monotonic emission/expiry, source state and counters. Records expire after 100ms; the one-second diagnostic output is not a continuous safety signal. A supervisor may run this sidecar independently of clients. Integration into the signed appliance source registry remains pending, so this command alone is not an installed vehicle/drone product.

For a library consumer, create `RosIngress`, pass it to `RosSubscriber` with an explicitly owned rclpy `Context`, and call `poll()`. The subscriber owns only its node/executor; the caller shuts down its context. All ingress operations belong to one executor thread. `poll()` returns one `RosObservation` or a fixed `SourceFault`. The latest pending payload replaces older unconsumed payloads; there is no growing frame queue.

## Timing and calibration

ROS acquisition stamps remain separate from local monotonic receipt. There is no automatic timestamp rebasing and no `/clock` simulation promotion. A caller may supply an expiring `ClockMapping(domain="ros_system", offset_ns=..., uncertainty_ns=..., valid_until_ns=...)` only with installation-specific clock evidence. Future/stale/duplicate/backwards timestamps withdraw that mapping. Mapped acquisition age plus uncertainty must fit the existing 100ms bound; uncertainty cannot exceed 50ms. Mapping and calibration expiry are checked again at consumption. Even an accepted mapping does not certify hardware or create semantic evidence.

The first CameraInfo contract is deliberately narrow: zero distortion, monocular identity rectification, canonical projection, matching dimensions/frame, no ROI or binning beyond one. Intrinsics expire locally and their digest/configuration changes break the scene. Distorted or stereo messages are rejected, not silently treated as rectified. Physical mount extrinsics, validated distortion correction and qualified model registration remain separate work.

Depth supports `16UC1` with explicit scale or `32FC1` metres; LWIR/NIR supports `mono8`/`mono16` counts. Counts are not radiometric temperature. Radar/LiDAR accepts the documented bounded x/y/z point-cloud subset, optionally signed radial velocity. Raw points do not establish pedestrian/UAV classes. See [sensor contracts](../../../docs/engineering/aethron-ecosystem/P2-SENSOR-ADAPTERS.md).

## Security and resource boundary

Subscriptions use BEST_EFFORT, VOLATILE, KEEP_LAST depth one with explicit topics. Parameter/logger services and rosout are disabled. There are no application command publishers, services or actions; rclpy still creates its standard parameter-events publisher and DDS has discovery traffic. Topic names/domain IDs are routing, not authentication. A production host must isolate DDS or provision authenticated middleware/security policy; do not expose an unauthenticated domain to an untrusted network.

Parser byte/point limits apply after DDS deserialization. They cannot prevent middleware allocation of an oversized wire message. The executed harness constrains the whole worker to 512MiB/two CPUs/96 processes, read-only root, UID 10001, no capabilities, no external network and bounded tmpfs. Native deployment needs equivalent process isolation and middleware limits. No raw image recording, identity metadata or network telemetry is added.

## Reproduce the installed SDK check

Build core/edge wheels twice with `SOURCE_DATE_EPOCH=1767225600`, prepare the hash-locked CPython 3.12 ARM64 wheel closure and explicitly pull the pinned image. Then run:

```sh
python scripts/edge_ros2_check.py --wheels build/ros/candidate \
  --dependencies build/ros/dependencies --out build/ros/check
```

The helper does not download anything. It mounts only wheels, tests and bootstrap files; it never mounts the source checkout. Original synthetic fixtures traverse real DDS and generated ROS messages before decoding. Portable tests also run against installed wheels. The dedicated [CI workflow](../../../.github/workflows/aethron-ros2-candidate.yml) repeats this procedure; hosted execution is pending until publication gates permit a push.

AETHRON source remains GPL-3.0-only with separately negotiated commercial licensing. ROS source is Apache-2.0; no SDK implementation or third-party sensor recording is bundled. [Recorded evidence](../../../docs/engineering/aethron-ecosystem/evidence/phase2/ros2.json) distinguishes software results, retained failures and pending field qualification.
