# C03 scalar geometry comparison

Use an environment containing the pinned edge dependencies and probe-only
NumPy 2.3.5 from the existing vision lock:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=integrations/edge \
  python scripts/probes/sensor_geometry_audit/compare.py
```

The probe checks 22 admission vectors and complete projection/deprojection/range
calls for 1 and 64 points. Each of 15 rotated samples averages 20 repetitions;
allocation tracing runs separately. NumPy is evaluated behind the same scalar
boundary, not as a redesigned batch API. Normal numerical outputs use 1e-14
relative tolerance; admission/error vectors match exactly. All inputs are
synthetic. No device, network or new production dependency is used.

The report retains a naive NumPy norm underflow counterexample. The timed
challenger uses stable hypot reduction, so it is not penalized for that known
incorrect candidate. The production regression can additionally be mutation
checked by replacing geometry.math.hypot with sqrt(sum(x*x)) during the test;
the tiny-norm cases must fail. This is candidate RED evidence, not a claim that
the existing production implementation failed.

Assertions must be enabled. Optimized execution/import (`-O`, `-OO` or nonzero
`PYTHONOPTIMIZE`) is rejected before exposing the comparison entry point. The
`parity` field covers the admission vectors and premeasurement warm-up only;
timed repetitions and traced outputs are not individually compared. A successful
report therefore does not prove parity of every measured call. The report retains
aggregate measurements, not the individual timing samples. Historical reports
are not requalified by the new mode guard.

The comparison requires exclusive process ownership of allocation tracing. It
rejects an active `tracemalloc` session before constructing cameras, preserving
the caller's traces. Each owned allocation pass stops tracing in `finally`,
including on candidate exceptions, interrupts and failed peak reads. This is
not synchronization against concurrent tracing changes. Reported traced peaks
are not total process/native memory or resource ceilings.

Focused evidence-admission checks (no timing matrix):

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH=integrations/edge:tests/integration \
  python -m unittest test_sensor_geometry_audit_modes
```

New reports include `source_sha256` for the harness and the actual imported
geometry module's on-disk file. Logical labels omit absolute paths. Hashing
occurs after admission checks and before measured batches; unavailable source
bytes prevent report emission. This is not executable attestation, report
authentication, a complete dependency closure or an atomic snapshot. Keep source
files stable during a run. The harness fingerprint covers the fixture-generation
code, not a separately serialized fixture artifact. Historical reports remain
unchanged. See the [partial source review](../../../docs/engineering/aethron-ecosystem/P21-GEOMETRY-SOURCE-EVIDENCE-V3.md).
