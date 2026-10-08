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

`deproject(u,v,axial_depth_m)` corrects the sparse ray, then uses supplied positive depth (up to the software envelope). Unknown/zero/nonfinite depth stays unknown. It does not infer depth from an intensity image. This increment does not remap a raster, compensate stereo baseline, support fisheye/rational lens models, rescale depth units, or automatically accept arbitrary ROS CameraInfo. Those models and the supervisor/provider connection remain executable follow-up work. The existing ROS ingress still rejects distorted CameraInfo until an explicit verified adapter connects it.

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

The edge CI matrix invokes this path. The ROS installed harness additionally runs the portable registration tests; it does not claim OpenCV testing inside the ROS image. [Evidence](evidence/phase2/registration.json) distinguishes executed checks and pending cells. Frozen core, model/dataset hashes, deadlines, recorded aircraft failures and prior latency/startup failures remain unchanged.
