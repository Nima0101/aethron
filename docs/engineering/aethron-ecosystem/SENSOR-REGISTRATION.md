# Sensor registration and sparse rectification — implemented software boundary

`aethron_edge.sensors.registration` transforms measured 3D points into a declared rectified optical plane. `aethron_edge.sensors.rectification` corrects sparse distorted image coordinates and deprojects explicit axial depth. Both are installed edge-package modules. This is partial P2.1: no semantic model, inferred object box/class, appliance source registration or hardware qualification is implied.

## Frames and persistent calibration

`RigCalibration` is a closed, immutable version-1 schema: source frame, target optical frame, mount identity, synthetic/recorded/external-unverified provenance, target `Pinhole`, row-major rotation, translation in metres and declared translation/rotation/reprojection error bounds. It applies `p_camera = R p_source + t`. Rotation must be orthonormal within numerical tolerance 1e-6 with determinant +1; scaling, shearing and reflections are rejected. The inverse uses `Rᵀ(p_camera − t)`. This is a rigid coordinate change, not ego-motion estimation or an assumption that sensors are co-located.

Optical axes are x right, y down, z forward. For ROS body x forward, y left, z up, the original test uses `R = [0,-1,0; 0,0,-1; 1,0,0]`. Never infer a frame convention from a product name or silently change units. [REP-103](https://www.ros.org/reps/rep-0103.html) is the convention source; its website denied automated access, so the pinned official repository text was read. Exact source provenance is recorded in [registration evidence](evidence/phase2/registration.json).

The artifact digest binds all fields. `load_calibration(bytes)` accepts at most 16KiB, rejects duplicate/unknown keys and nonfinite/boolean numeric inputs, and reports only a fixed failure. It loads no files or network locations. A digest detects a change; it does not authenticate a calibration or prove its accuracy. The artifact contains no host-monotonic expiry that could accidentally survive a reboot.

## Local binding and failure behavior

`Registration(calibration, now_ns=..., valid_for_ns=..., clock_id=...)` binds the artifact to a local clock domain for at most 600 seconds. Callers must use the local trusted monotonic clock and rebind after boot/configuration changes. Each `project()` call requires source frame, mount ID, matching clock ID, acquisition time and uncertainty. Acquisition age plus uncertainty must fit the existing 100ms limit; uncertainty must be at most 50ms and the latest possible acquisition cannot be in the future. Monotonic rewind closes the binding permanently. Expiry, frame/mount/clock mismatch, invalid geometry and source loss return a fixed `registration_unavailable` fault and break scene continuity. A new binding starts a new scene; the module retains no point or object history.

Output includes camera coordinates, pixel coordinates, width/height-normalized coordinates, declared metric error radius, conservative pixel bounds, computed camera-origin range, calibration digest and expiry. The range is a geometric calculation from supplied measured coordinates, not a new physical range measurement. `live_evidence` is always false. No covariance/probability is invented from an error bound.

For measurement error radius `e`, translation error `t_e`, angular rotation error `θ` and source point `p`, the propagated radius is `e + t_e + 2 sin(θ/2) ||p||`. A containing coordinate box is projected with denominator extremes and expanded by the declared reprojection error. An uncertainty region crossing the camera plane or image border is rejected rather than clipped into a deceptively precise point. These bounds are conditional on the supplied error declarations and model; they are not an empirical calibration certificate. The 500m point envelope is an inherited software limit, not a sensor range claim.

## Lens rectification

`LensCalibration` carries source/output pinholes, five Brown-Conrady coefficients `(k1,k2,p1,p2,k3)` and an explicit valid normalized radius. It uses the already pinned optional OpenCV vision dependency; base edge installation does not import OpenCV. At most 4,096 points enter a native call. Dimensions, finite coordinates and input/output image domains are checked.

Before inversion, a conservative lower bound on the distortion Jacobian must remain positive over the declared disk. Negative radial terms are bounded at the outer radius; tangential terms use a conservative matrix-norm bound. This rejects folded or poorly bounded models even when a few central points look plausible. `undistortPointsIter` uses a fixed 50-iteration/1e-10 termination criterion and independently checks forward reprojection residual at 1e-6 pixel. Non-convergence or out-of-domain output fails closed. These are numeric software checks chosen before evaluation, not a field accuracy guarantee. The identity test permits floating-point roundoff to 1e-10 pixel; its initial exact-equality failure is retained.

`deproject(u,v,axial_depth_m)` corrects the sparse ray, then uses supplied positive axial z-depth (up to the software envelope). Unknown/zero/nonfinite depth stays unknown; radial range must not be supplied as axial depth. It does not infer depth from an intensity image. Recorded mono8 raster remapping is described below; stereo baseline compensation, rational lens models and automatic distorted ROS CameraInfo admission remain pending.

`FisheyeCalibration` adds a separate required `model="opencv_fisheye_v1"` tag, four angular coefficients `(k1,k2,k3,k4)`, source/output pinholes and `valid_theta_rad` in `(0, atan(3)]`. Zero coefficients describe an equidistant lens, not an identity pinhole transform. Skew is unsupported. Admission requires a conservative positive lower bound on the angular derivative and a distorted angular endpoint below π/2. This avoids folded inverses and the native solver's clipped domain. The same point count, image bounds, iterations, residual check and axial-depth limits apply. Unsupported or unavailable inversion withdraws geometry; it never returns a guessed ray.

`ProviderCalibration.lens` accepts either model and binds its full declaration into the calibration digest. The old untagged five-coefficient Brown schema and no-lens digests remain unchanged. Recorded depth bytes are corrected before the rig transform; existing provenance, error declarations and expiry remain binding. Sparse replay does not establish physical calibration or extend an expired sensor lease. The [fisheye evidence](evidence/phase2/fisheye.json) records the initial Mac numerical and Linux schema checks; subsequent [raw-depth evidence](evidence/phase2/raw-depth-dds.json) adds Linux numerical/DDS execution and retains a combined CLI clock-drift failure.

The provider batches its at-most-64 selected valid depth pixels into one native inversion. Unknown depth stays unknown and is excluded from inversion; selection order and each point's axial depth are preserved. Processing expiry is checked after the complete batch. [Batching evidence](evidence/phase2/batched-rectification.json) uses real inversion with deterministic injected per-call cost to test deadline behavior; this is not a measured latency or physical timing guarantee.

Angular semantics follow [OpenCV 4.13.0 fisheye documentation](https://docs.opencv.org/4.13.0/db/d58/group__calib3d__fisheye.html); clipping and convergence behavior were checked against the [4.13.0 implementation](https://github.com/opencv/opencv/blob/4.13.0/modules/calib3d/src/fisheye.cpp), retrieved 2026-10-09. These are software domain checks, not measured lens accuracy.

## Explicit raw ROS depth binding

The library path `RosIngress(..., raw_depth_lens=lens)` accepts depth only and requires the caller to select a raw distorted stream. CameraInfo cannot enable this mode. Its model (`plumb_bob` or `equidistant`), coefficients, source dimensions/K and output P must exactly match the declared lens; R must be identity, stereo translation/skew/cropping/subsampling remain unsupported. Configure the same lens in `ProviderCalibration`. Missing, mismatched, expired or unavailable correction returns a fixed fault and withdraws geometry. Default ingress still rejects distortion. The metadata cannot prove what a physical publisher sends; installation verification and publisher authentication remain separate.

Each queued observation now captures its calibration expiry. Later matching CameraInfo can authorize fresh frames but cannot extend old queued or already emitted geometry. Shortened or revoked current leases still apply. Lens declarations enter calibration identity; legacy no-lens identity remains unchanged. Outputs retain `external_unverified` provenance and do not infer object classes.

ROS [Jazzy CameraInfo](https://github.com/ros2/common_interfaces/blob/jazzy/sensor_msgs/msg/CameraInfo.msg) defines raw K and rectified P separately. The official [image_geometry implementation](https://github.com/ros-perception/vision_opencv/blob/rolling/image_geometry/src/pinhole_camera_model.cpp) maps `equidistant` to OpenCV fisheye (retrieved 2026-10-09; reference semantics, not an added rolling dependency). [Library evidence](evidence/phase2/ros-lens.json) separates installed message-boundary tests from DDS and physical qualification. Version-1/2 appliance manifests still reject lenses; [version-3 raw provisioning](ROS-APPLIANCE.md) now connects explicit raw configuration to the worker. Focused raw DDS and signed CLI execution are recorded above; full candidate boot qualification remains pending.

The native algorithm and coordinate model follow [OpenCV 4.13.0 calibration documentation](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html), read 2026-10-08. AETHRON implementation remains GPL-3.0-only; existing OpenCV/NumPy license records and dependency pins are unchanged.

## Installed example

After building/installing the local core and edge candidate wheels with the locked vision extras:

```python
from aethron_edge.sensors.geometry import Pinhole
from aethron_edge.sensors.rectification import LensCalibration

camera = Pinhole(width=640, height=480, fx=400.0, fy=400.0, cx=320.0, cy=240.0)
lens = LensCalibration(camera=camera, output_camera=camera,
                       distortion=(0.1, 0.0, 0.0, 0.0, 0.0), valid_radius=1.0)
xyz = lens.deproject(400.4, 280.2, 5.0)  # original synthetic ray -> approximately (1, .5, 5)
```

Original integration fixtures exercise raw `16UC1` bytes → explicit depth scale → rectified ray → translated rig → target pixel, including unknown depth. Installed checks run portable registration tests without vision extras first, then install the hash-locked optional closure and run actual native rectification outside the checkout:

```sh
python scripts/edge_package_check.py --vision --out build/registration-package
```

The edge CI matrix invokes this path. The ROS installed harness now includes the locked vision closure and numerical tests; full updated pinned-base/hosted execution remains pending. The focused retained-guest runs above are separate evidence. Frozen core, model/dataset hashes, deadlines, recorded aircraft failures and prior latency/startup failures remain unchanged.

## Recorded intensity raster v1

`aethron_edge.sensors.raster_rectification.rectify_mono8_recorded(raster, lens)`
adds explicit recorded LWIR/NIR `mono8` remapping for either existing lens model.
Input dimensions must match the source camera. Each output integer pixel centre
maps through the declared forward distortion into source coordinates. Brown
rays outside `valid_radius`, fisheye rays outside `valid_theta_rad`, and continuous
coordinates outside the source image are invalid; they are never clamped inward.
Valid coordinates use nearest-neighbour sampling (`floor(coordinate + 0.5)`),
preserving a source count without interpolation, normalization or temperature
conversion. Row padding is ignored. Sampling displacement is at most half a pixel
per source axis, not a physical calibration-error estimate.

The immutable `RectifiedMono8` result has version 1, dimensions, modality, packed
`data`, and one `validity` byte per pixel (0 invalid, 1 valid). Invalid storage is
zero, which is **not evidence**: preserve the mask when using the buffers.
`sample(x, y)` returns `None` for invalid pixels and preserves a valid zero count.
`live_evidence` is always false. No timestamp, calibration lease, signed authority,
model capability or live-provider admission is created by this utility.

Input retains the existing 8 MiB/1920×1080 layout limits; output is limited to
640×512 total pixels (327680), within existing camera dimension bounds. One pass
uses two bounded byte buffers and no persistent map/cache. This is a work/memory
bound, not latency qualification. The implementation uses the already documented
forward Brown-Conrady and OpenCV angular equations without a native solver or new
dependency. Sparse rectification APIs and their domains remain unchanged. Stereo,
depth raster resampling and live raster admission remain pending.

`rectify_mono16_recorded(raster, lens)` is the separate mono16 entry point. It
accepts only LWIR/NIR `mono16` layouts with explicit input byte order and returns
`RectifiedMono16` version 1: packed **little-endian** unsigned 16-bit counts,
`encoding="mono16"`, `is_bigendian=False`, and the same one-byte-per-pixel mask.
`sample(x, y)` returns the original integer in 0–65535 or `None`; zero remains a
valid intensity count. Byte-order conversion never normalizes, clips, scales,
or interprets counts as temperature or depth. Padded input rows are supported;
output has no padding. Each entry point rejects the other encoding and all depth
encodings. Mono8 v1 output bytes and mask semantics are unchanged.

Mono16 uses the same nearest-neighbour mapping, calibrated-domain checks and
327680-output-pixel ceiling. At that ceiling, packed data occupies 655360 bytes
and the validity mask 327680 bytes; constructing immutable results also briefly
retains the mutable buffers. No map cache, native dependency, timestamp renewal
or live-evidence authority is introduced.

### Calibration-bound recorded intensity replay v1

`aethron_edge.sensors.intensity_replay.IntensityCalibration` is a separate closed
recorded-intensity contract: required integer `version=1`, `source_id`,
`coordinate_frame`, complete `ImageLayout`, and Brown or fisheye `lens`. It
accepts only LWIR/NIR intensity layouts matching the source camera dimensions
and the existing output-pixel limit. It does not extend `ProviderCalibration`.
Its `digest` is SHA-256 of the UTF-8 prefix
`aethron-recorded-intensity-v1\n` followed by the validated model's JSON with
sorted keys, compact separators and non-finite numbers forbidden. The layout,
both cameras, coefficients, lens model/domain and source/frame binding are all
covered. JSON calibration files can be loaded with `model_validate_json`.

`rectify_recorded_intensity(frame, calibration,
expected_calibration_sha256=independently_pinned_digest)` verifies equality of
that pin, the complete calibration digest and the raw replay header's
`calibration_sha256`. It revalidates Python-constructed frames/calibrations,
matches source, coordinate frame and layout, and verifies the raw payload hash
before remapping. The pin must come from a separate expected-calibration record;
deriving it from the supplied recording defeats mismatch detection. Neither
checksums nor this pin verify signatures, ownership or physical calibration.

The returned `RecordedIntensity` contains `raster`, `calibration` and
`source_header`. The latter describes the **original raw recording**, including
its original payload hash and layout; it is not an output-raster header.
Acquisition time, uncertainty, sequence and recorded clock domain are preserved.
The result retains no raw payload, has `source_evidence="recorded"` and
`live_evidence=False`, and retains the raster's validity mask. Pass frames from
`read_frames` to retain that reader's stream continuity checks; this per-frame
operation creates no clock, freshness lease, stream history or live authority.

Inspect selected output pixels offline (counts or JSON `null` for invalid rays):

```sh
python -m aethron_edge.sensors.intensity_inspect \
  --recording raw.bin --calibration intensity-calibration.json \
  --expected-calibration-sha256 "$EXPECTED_CALIBRATION_SHA256" \
  --pixel 0 0 --pixel 10 20 --max-frames 10
```

The expected digest must be independently pinned. Limits are 64 MiB input,
64 KiB calibration, 1–64 selected pixels, and 1–300 frames (default 1) within
the existing 30-second recorded envelope. Extra frames fail rather than truncate.
The command emits one JSON document only after complete success; errors return
exit 2 without partial stdout or input echo. It opens regular local files only,
does not activate devices, and retains only selected counts plus source metadata
between frames. All output remains recorded and non-live.

An explicit optional [C++20 Brown backend](../../../integrations/native-raster/README.md)
is available as a separate platform wheel. It preserves the recorded mono8/mono16
result contract and uses the unchanged Python validation boundary. Installation
never switches the default path; fisheye, live/ROS admission and signed provenance
remain separate. Its exact-build synthetic measurements and limitations are in
[the native evidence](../../../integrations/native-raster/evidence/macos-arm64.json).

### Registration binding validation correction (2026-10-09)

`Registration` now reconstructs and validates the supplied rig, including its
nested camera, before issuing a process-local binding. Pydantic's
[`model_copy` and `model_construct`](https://docs.pydantic.dev/latest/api/base_model/)
can bypass validation even for frozen models. Previously a Python caller could
bind negative error bounds, an improper rotation or an invalid camera that the
JSON loader would reject. The constructor now returns only `invalid_calibration`
for those inputs, without serialization warnings or private input details.

The existing strict schema is the validation authority. Rebuilding from field
data is necessary because accepting an existing model instance does not ensure
nested field validation. This bounded rig contains one camera and a fixed-size
transform; validation runs once per binding, outside the per-point path. No new
dependency, schema, threshold, calibration authority or hardware claim is added.
The focused Linux checks and retained environment failure are recorded in
[binding-validation evidence](evidence/phase2/registration-binding-validation.json).
