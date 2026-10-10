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
