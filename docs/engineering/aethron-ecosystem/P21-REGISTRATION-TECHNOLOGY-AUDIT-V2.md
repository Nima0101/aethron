# P2.1 C04 calibration and registration — audit policy v2

Decision: **KEEP strict Python admission and scalar registration; implement a
read-only validated calibration snapshot and reuse its digest per binding.**
This covers persistent rig loading, rigid transform/inverse, declared uncertainty,
process-local lease and provenance output, including the earlier nested-model
validation repair. C05–C09 remain pending; no forward feature expansion.

## Constraints and findings

Linux offline, thread-confined bindings, no device SDK or actuation. Rig JSON is
bounded to 16 KiB, rejects duplicate keys and unknown/invalid fields, and carries
one fixed 3×3 rotation, translation, camera and declared error bounds. Rotation
must meet the frozen 1e-6 orthogonality/determinant tolerance; reflections and
scaling are rejected rather than repaired. Points stay within the 500 m software
envelope. A caller typically selects at most 64 points per frame.

The binding revalidates copied/constructed nested models, validates exact integer
clocks, caps lifetime at 600 seconds, withdraws stale/future/wrong-frame/mount/clock
inputs and permanently closes after a clock rewind. Error bounds include declared
translation, rotation and measurement error; plane crossing or image-domain
uncertainty withdraws geometry. Outputs preserve digest, expiry and scene-break
semantics and never self-certify live hardware. The v1 JSON digest encoding must
remain byte-compatible; replacing it with another canonicalization is not allowed.

Two defects in the existing ownership/work model were identified: callers could
assign a replacement to an active binding's public `calibration`, bypassing the
constructor's validation/rebinding path; every successful point also serialized
and hashed the same immutable calibration. The latter is unnecessary per-point
work, not a requirement for provenance freshness.

## Candidate assessment

| Candidate | Evidence and decision |
| --- | --- |
| Python/Pydantic plus scalar geometry, digest once per binding | Executable improvement; keeps strict schema reconstruction, exact integer state, existing digest bytes and immutable output. Selected after comparison. |
| NumPy matrix transform | Executed behind full registration, retaining `_point` admission and output conversion. Tested both per-call array creation and a favorable variant with matrix/translation arrays prepared outside timing. Neither improves this selected-point path in the observed run. |
| SciPy Rotation | Official API may orthogonalize invalid matrices; that behavior conflicts with reject-not-repair admission unless surrounded by the existing checks. No fit/rotation-estimation operation is required here. Not used as a direct replacement. |
| Julia IntervalArithmetic | Credible non-incumbent technology for rigorous enclosures. A different numerical guarantee could justify a versioned migration, but this audit does not claim an executed interval implementation or interchangeability with the frozen declared-error formulas. Source comparison only. |
| Boost.Interval with fixed native geometry | Credible native interval substrate; correctness depends on rounding policy and compiler/target support. Source comparison only, not a measured native latency result or automatic safety qualification. |

Primary sources:

- [Pydantic model immutability and construction](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability)
  explain why `frozen` is not a universal tamper-proof boundary and why unchecked
  models must be reconstructed. This implementation owns a fresh validated
  snapshot and prevents public attribute replacement; it does not defend against
  hostile code modifying private Python internals in the same process.
- [NumPy matrix multiplication](https://numpy.org/doc/stable/reference/generated/numpy.matmul.html)
  supplies the executed numerical challenger. Conversion and strict admission
  remain measured parts of the full registration path.
- [SciPy Rotation.from_matrix](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.from_matrix.html)
  documents estimation of a rotation when input is not orthogonal. That is not
  the frozen admission behavior required here; it does not imply SciPy cannot
  be wrapped safely. No SciPy dependency was installed.
- [Julia IntervalArithmetic](https://juliaintervals.github.io/IntervalArithmetic.jl/stable/)
  provides validated interval numerics. [Boost.Interval](https://www.boost.org/doc/libs/latest/libs/numeric/interval/doc/interval.htm)
  documents inclusion/rounding policies and target/compiler caveats. No new
  interval runtime was installed and no rigorous floating-point enclosure proof
  or physical calibration guarantee is inferred from the present formulas.

The decision is based on measured complete-path cost, admission/provenance
semantics and the absence of a required fit/solver or array-native consumer.
Existing language, installed tools and rewrite cost are not selection criteria.
It is not a performance ranking of unexecuted Julia/native alternatives. Future
rigorous interval or fused batch requirements must be separately evidenced;
no frozen tolerance was changed to favor this result.

## Executed selection and change

The synthetic comparison runs 64 projected points, including binding creation,
strict validation, uncertainty bounds, SHA output and result construction. Fifteen
rotated samples compare scalar and NumPy transforms. Before implementation,
median CPU was 3.771 ms scalar and 5.879 ms NumPy; substituting a precomputed
fixture digest reduced scalar CPU to 1.685 ms. This prototype was not production
caching: it deliberately supplied a known constant for the one synthetic rig.

Production now stores the digest of its own freshly validated snapshot once in
`Registration.__init__`. A read-only property preserves access to `calibration`;
assignment raises `AttributeError`. A different calibration requires a new
binding and starts with a scene break. Projection copies the stored digest into
its result without JSON serialization. Public schema, transform arithmetic,
uncertainty/time thresholds, expiry and checksum format are unchanged.

The final implementation measured 1.409 ms scalar, 2.845 ms NumPy and 2.175 ms
NumPy with prebuilt arrays. Complete outputs matched for the synthetic fixture.
Earlier post-change observations are retained as well. Separate run windows and
shared-host contention prevent treating these timings as a precise universal
speedup or deadline guarantee. The probe is an identity-rotation translated-rig
workload; rotation diversity, malformed input and time faults are covered by the
focused tests, not represented as performance coverage.

Both new regressions failed before the fix: active calibration assignment was
accepted, and point projection invoked JSON serialization. Afterward, 46 focused
registration/geometry/packet/provider tests and 15 installed-wheel registration
tests passed, with Ruff lint/format and production Bandit. The earlier copied and
constructed nested-model negatives and 2000 bounded invalid-geometry cases still
pass. Historical T10 latency and signed radar startup failures remain retained.
No hardware, legal, certification or physical accuracy gate is cleared.

[Probe](../../../scripts/probes/sensor_registration_audit/README.md) ·
[Executed evidence](evidence/phase2/technology-v2-registration.json)
