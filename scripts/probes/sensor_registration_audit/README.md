# C04 registration comparison

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=integrations/edge \
  python scripts/probes/sensor_registration_audit/compare.py
```

Use the edge package's pinned dependencies and probe-only NumPy 2.3.5 from the
vision lock. No new production dependency, network or device input is used.
The synthetic rig uses identity rotation and a translation. Each of 15 rotated
samples includes binding creation and 64 complete projections. All complete
results must match, including provenance, expiry and scene-break fields.

`numpy_transform` creates arrays per call; `prepared_numpy_transform` deliberately
excludes matrix/translation setup to favor that challenger. `cached_*_prototype`
substitutes a known digest for the single fixture and is only a selection probe,
not a deployable provenance cache. After the production fix it changes only the
constructor's digest calculation, so compare before/after evidence with that
limitation in mind. Production always computes its own validated snapshot digest.

The report records process CPU medians, not RSS or hardware deadlines. Source
rotation/admission and fault coverage lives in test_sensor_registration.py; this
single fixture is not broad performance or physical calibration evidence.
