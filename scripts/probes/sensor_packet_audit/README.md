# C01 raw-packet technology comparison

Synthetic, bounded audit prototypes; not production transports or qualification.
The Node worker accepts only the trusted fixed-size fixtures from `compare.py`.
It does not validate arbitrary input metadata. Both fixtures contain 4096 points,
241 invalid ordinals, row padding and reordered fields; the second uses mixed
widths, unaligned fields and big-endian encoding. No device or network is used.

Use a Python environment with the edge package/Pydantic and NumPy 2.3.5 from the
hash-pinned `integrations/edge/requirements-vision.lock`, plus Node.js. The recorded
run used Python 3.13.13 and Node v22.23.2. No product dependency is added.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=integrations/edge \
  python scripts/probes/sensor_packet_audit/compare.py > packet-comparison.json
node --check scripts/probes/sensor_packet_audit/buffer_worker.cjs
```

The harness compares complete validated Python results and reports 15 rotated
samples per case. Node is persistent; cold startup and worker RSS are reported
separately. Combined CPU includes Python parent and Node decode/encode kernel,
**excluding worker pipe-I/O CPU**, so it is a lower bound. NumPy's strided view
avoids flattening copies; list/result conversion is measured. Wall p95 is the
largest of 15 samples. Shared-host timing is not a deadline guarantee.

The retained original scalar decoder is the baseline. `production` invokes the
real installed/source decoder; `compiled_struct` is an independent prototype of
the selected mechanism. The comparison only informs this existing object ABI;
array-native downstream processing needs its own audit.
