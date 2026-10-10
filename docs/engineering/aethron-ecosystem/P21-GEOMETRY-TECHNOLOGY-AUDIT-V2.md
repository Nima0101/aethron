# P2.1 C03 pinhole geometry — retrospective technology audit v2

This document records a **historical V2 checkpoint**, not current V3 completion.
See the [partial V3 qualification review](P21-GEOMETRY-CLAIMS-REVIEW-V3.md).

The V2 decision was **KEEP** the scalar Python boundary with the native
`math.hypot` range kernel.
No production migration wins on the evidence below. Executable challenger and
numeric regression tests substantiate that decision; this is not an automatic
endorsement of every numerical component. At that checkpoint C04–C09 were
unaudited. These historical statements do not advance the fresh V3 review.

## Deployment and actual workload

`geometry.py` implements rectified optical projection, deprojection and Euclidean
range. It does not fit calibration, transform extrinsics, compensate distortion,
process whole rasters or qualify sensors. Width/height are bounded to 1920/1080;
positive focal lengths are bounded to 100000. Deprojection requires in-image
pixels and depth in (0,500]; range requires a finite positive result <=500 m.
Projection requires positive Z and an in-image result; it does not itself
enforce the range limit. The 500 m checks define numerical acceptance only,
not measured sensor reach or calibration accuracy. The methods reject boolean
coordinates, nonfinite or malformed input and nonfinite arithmetic results.

The observed registration caller projects one already-transformed point, then
computes range and separate conservative uncertainty bounds. The provider calls
these methods for 1–64 selected indices. Rectification consumers also use scalar
methods; full-raster numerical work is a separate audited component. The current
public interface returns tuples/scalars, not array views. Correct abstention at
image boundaries, float64 arithmetic, bounded allocations and deterministic
exceptions matter more here than matrix throughput. Linux offline deployment
has no required device SDK or background service; the historical shared host
reported 6.3 GiB RAM. This is not a deployment memory guarantee.

## Independent technology candidates

- **Scalar Python/native math:** [the math library](https://docs.python.org/3/library/math.html#math.hypot)
  supplies a numerically stable norm. Existing projection/deprojection are
  explicit scalar expressions, not matrix loops. Complete calls, validation and
  immutable results are included in the executed comparison.
- **NumPy:** [matrix operations](https://numpy.org/doc/stable/reference/generated/numpy.matmul.html)
  are credible for batches. The executed challenger preserves the current scalar
  API, uses arrays for projection/deprojection and stable `hypot.reduce` for
  range. NumPy 2.3.5 is already hash-pinned in the vision lock and was installed
  only in the prior probe environment. It is not added to the base packet API.
- **Julia StaticArrays:** [the primary documentation](https://juliaarrays.github.io/StaticArrays.jl/stable/)
  describes fixed-size small-vector specialization, unrolling and temporary
  allocation elimination. This is a serious candidate beyond the incumbent
  language, especially if a future fused geometry workload emerges. The present
  formulas are already scalar/unrolled and still need strict boundary admission
  and result ownership. No Julia benchmark or inferred startup/memory figure is
  claimed; source review alone does not establish a material end-to-end win.
- **Eigen:** [fixed-size typed vectors/matrices](https://libeigen.gitlab.io/eigen/docs-nightly/group__TutorialMatrixClass.html)
  can express projection with inline storage and compiled operations. A native
  binding would still need finite/type/domain guards and safe ownership. This
  component has no matrix solve or large batch to demonstrate an advantage over
  its handful of scalar operations. Source comparison only; no native-speed
  inferiority or safety guarantee is asserted.
- **OpenCV calib3d:** [pinhole/projective geometry](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html)
  supplies projection and broader calibration machinery. Its scope includes
  extrinsics, distortion and Jacobians. Adopting it does not replace this API's
  positive-Z, finite and image-domain admission. No calibration solver, distortion
  model or image processing SDK is required by C03, so that additional dependency
  surface has no demonstrated benefit here. Source comparison only.

No choice rests on installed tooling, language familiarity or rewrite cost.
The conclusion is component-specific: preserve the minimal, measured scalar
path. A redesigned vectorized/batched interface is not benchmarked here and
could change the decision; its consumers and uncertainty contracts would need
explicit migration evidence. This audit does not claim all alternatives are
slower or mechanically enumerate languages.

## Executed comparison and numeric evidence

The probe compares complete project/deproject/range operations, including strict
admission and tuple/scalar conversion. It checks 22 accepted/rejected vectors,
then 15 rotated timing samples with 20 repetitions each at 1 and 64 selected points.
Tracing is measured separately. Both implementations pass the 22 contract cases;
ordinary result parity uses relative tolerance 1e-14, while admission boundaries
and error categories must agree exactly.

| Operations per sample | Scalar CPU median | NumPy scalar CPU median | Traced peak scalar / NumPy |
| --- | ---: | ---: | ---: |
| 1 | 0.00522ms | 0.04153ms | 576 / 1088 bytes |
| 64 | 0.30825ms | 2.61305ms | 6368 / 10320 bytes |

These are synthetic, shared-host observations, not frozen deadline qualification,
RSS accounting or a vectorized NumPy throughput comparison. Warm calls exclude
imports and camera construction. The retained JSON contains medians rather than
the individual timing samples; it cannot independently reproduce their spread
or establish worst-case execution time. The existing C01 import probe also observed
additional NumPy residency, but no memory measurement is fabricated for Julia,
Eigen or OpenCV.

The initial naive squared-sum norm computes zero for (1e-300,0,0), while `hypot`
returns 1e-300. A mutation replacing the production hypot with that candidate
fails two new tiny-vector cases, including the smallest positive subnormal.
The NumPy challenger was corrected to `hypot.reduce` **before** comparing it;
it is not rejected using a deliberately inferior norm. Production remains
unchanged because its algorithm already meets the demonstrated contract.

Five new regression tests cover tiny norms, Euclidean versus axial range,
next-representable values beyond range/image limits, arithmetic overflow and
corner round trips. 28 focused packet/geometry/registration tests passed. An
installed wheel is checked independently; lint/format and production security
results are recorded in the [evidence](evidence/phase2/technology-v2-geometry.json).
[Probe instructions](../../../scripts/probes/sensor_geometry_audit/README.md)
reproduce the comparison and distinguish the mutation from a production defect.

Earlier T10 latency and signed radar startup failures remain unresolved by these
checks. No bounds changed. No hardware/calibration/accuracy claim is made.
