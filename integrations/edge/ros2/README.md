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

Use the actual sensor scale, frame ID and topic; 0.001 is an example, not a device default. The process runs until terminated and handles SIGTERM cleanly. It emits pixel-free status records with host-monotonic emission/expiry, source state and counters. Records expire after 100ms; the one-second diagnostic output is not a continuous safety signal. A supervisor may run this sidecar independently of clients. The separate `sensor-ros` appliance driver now connects this provider to the signed source registry; see the [ROS appliance guide](../../../docs/engineering/aethron-ecosystem/ROS-APPLIANCE.md). The sidecar alone is not an installed vehicle/drone product.

For a library consumer, create `RosIngress`, pass it to `RosSubscriber` with an explicitly owned rclpy `Context`, and call `poll()`. The subscriber owns only its node/executor; the caller shuts down its context. All ingress operations belong to one executor thread. `poll()` returns one `RosObservation` or a fixed `SourceFault`. The latest pending payload replaces older unconsumed payloads; there is no growing frame queue.

## Timing and calibration

ROS acquisition stamps remain separate from local monotonic receipt. There is no automatic timestamp rebasing and no `/clock` simulation promotion. A caller may supply an expiring `ClockMapping(domain="ros_system", offset_ns=..., uncertainty_ns=..., valid_until_ns=...)` only with installation-specific clock evidence. Future/stale/duplicate/backwards timestamps withdraw that mapping. Mapped acquisition age plus uncertainty must fit the existing 100ms bound; uncertainty cannot exceed 50ms. Mapping and calibration expiry are checked again at consumption. Even an accepted mapping does not certify hardware or create semantic evidence.

The default CameraInfo contract requires zero distortion, monocular identity rectification, canonical projection, matching dimensions/frame, no ROI or binning beyond one. Version-3 raw-depth manifests explicitly bind a Brown or fisheye lens calibration and correct selected axial-depth samples; all CameraInfo fields must match that provisioned model. Intrinsics expire locally and their digest/configuration changes break the scene. Undeclared distortion and stereo messages remain rejected. Sparse numerical correction does not qualify physical calibration, raster rectification or model registration.

Depth supports `16UC1` with explicit scale or `32FC1` metres; LWIR/NIR supports `mono8`/`mono16` counts. Counts are not radiometric temperature. Radar/LiDAR accepts the documented bounded x/y/z point-cloud subset, optionally signed radial velocity. Raw points do not establish pedestrian/UAV classes. See [sensor contracts](../../../docs/engineering/aethron-ecosystem/P2-SENSOR-ADAPTERS.md).

## Security and resource boundary

Subscriptions use BEST_EFFORT, VOLATILE, KEEP_LAST depth one with explicit topics. Parameter/logger services and rosout are disabled. There are no application command publishers, services or actions; rclpy still creates its standard parameter-events publisher and DDS has discovery traffic. Topic names/domain IDs are routing, not authentication. A production host must isolate DDS or provision authenticated middleware/security policy; do not expose an unauthenticated domain to an untrusted network.

Parser byte/point limits apply after DDS deserialization. They cannot prevent middleware allocation of an oversized wire message. The executed harness constrains the whole worker to 512MiB/two CPUs/96 processes, read-only root, UID 10001, no capabilities, no external network and bounded tmpfs. Native deployment needs equivalent process isolation and middleware limits. No raw image recording, identity metadata or network telemetry is added.

## Reproduce the installed SDK check

At full candidate qualification, build core/edge wheels twice with `SOURCE_DATE_EPOCH=1767225600`. For a focused installed consumer, reuse byte-verified unchanged candidate wheels. Prepare both hash-locked CPython 3.12 ARM64 closures (`requirements.lock` and `../requirements-vision.lock`) and explicitly pull the pinned image. The vision wheels require the `manylinux_2_28_aarch64` platform, CPython 3.12 and `cp312`/`abi3` tags. The harness installs them offline and tests Brown/fisheye numerical correction, actual raw-depth DDS and signed version-3 CLI operation. Its tmpfs allowance is 256MiB to hold the added native wheels; the process memory/CPU/PID and timing limits remain unchanged. Then run:

```sh
python scripts/edge_ros2_check.py --wheels build/ros/candidate \
  --dependencies build/ros/dependencies --out build/ros/check
```

The helper requires a fresh `--out` directory and refuses an existing directory or symlink before copying inputs or starting a container. This preserves previous evidence and prevents stale wheels/tests or a prior successful report from being mixed with a failed new run. It does not download anything. It mounts only wheels, tests and bootstrap files; it never mounts the source checkout. Original synthetic fixtures traverse real DDS and generated ROS messages before decoding. Portable tests also run against installed wheels. The dedicated [CI workflow](../../../.github/workflows/aethron-ros2-candidate.yml) repeats this procedure; hosted execution is pending until publication gates permit a push.

AETHRON source remains GPL-3.0-only with separately negotiated commercial licensing. ROS source is Apache-2.0; no SDK implementation or third-party sensor recording is bundled. [Recorded evidence](../../../docs/engineering/aethron-ecosystem/evidence/phase2/ros2.json) distinguishes software results, retained failures and pending field qualification.

The installed lane now includes the existing full server dependency closure and the real signed appliance CLI with original synthetic DDS publishing, authenticated HTTP/SSE, zero-viewer continuation and configuration/signature tamper rejection. No temporary private key or source checkout enters the retained artifact bundle. This does not close continuous ROS authority renewal, Mac availability, new boot-soak or physical qualification gates.

The focused [raw-depth evidence](../../../docs/engineering/aethron-ecosystem/evidence/phase2/raw-depth-dds.json) records installed Linux numerical/DDS checks and a passing isolated signed CLI run using the retained guest image. Its combined run failed the unchanged clock-drift gate; the isolated pass does not resolve that timing failure. The updated full pinned-image harness, hosted CI, boot/reboot and soak qualification remain pending.

The subsequent [complete bundle check](../../../docs/engineering/aethron-ecosystem/evidence/phase2/ros-bundle-output.json) ran 121 tests on the retained guest: 120 passed and the raw signed CLI failed with source-clock discontinuity. An instrumented repeat passed all 121 without reproducing the fault. Both results are retained; neither qualifies continuous availability or replaces the pending canonical pinned-base run.

For a timing failure, repeat into a fresh output directory with `--diagnostics`. The signed CLI tests then provision a temporary test-only startup hook; the product wheel is unchanged. Each process emits at most eight fixed-schema timing records containing age, uncertainty, sample duration and timestamp deltas—no raw timestamps, payloads, identities or exception text. The collector reads only the last 64KiB of the local test log and retains at most eight validated records. The result marks `diagnostic_instrumentation: true`; instrumentation can affect scheduling and is not a substitute for an uninstrumented run. Default runs do not install the hook.

For clock-instability diagnosis independent of ROS, run `python packaging/appliance/image/clock_check.py` inside the intended guest with the edge package installed. It samples monotonic/realtime pairs 1,501 times, 20 ms apart (about 30 seconds), using the runtime sampling function and a fixed 1 ms drift budget. `--samples` accepts 2–1501. Exit 1 means a sample was rejected; exit 0 only means this sampling window stayed within budget. The fixed JSON summary retains at most eight numeric rejection records and no absolute timestamps. The first reference offset never resets, and the check never issues authority, modifies OS time or qualifies hardware. Use an external timeout when running in a guest that may stall; retain failures instead of retrying to obtain a pass.
