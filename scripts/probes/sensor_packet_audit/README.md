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

Worker-reported CPU duration must be finite and nonnegative before it can enter
the comparison. This admission check does not authenticate the worker's clock or
prove a plausible upper bound. Historical reports are not requalified by it.

After a worker is created, handshake or startup-metadata failures invoke
`close()` before constructor failure propagates, including interrupts. Cleanup
attempts waiting even if stdin closure raises; it attempts both output-pipe
closures even if process cleanup or stdout closure raises. Both waits specify
five-second timeouts, including the wait after killing the child. Cleanup can
itself fail and supersede an earlier error, with exception context retained.
Focused tests use fake processes and pipes; they do not qualify OS shutdown
behavior. Pipe closure, scheduling and other OS calls have no measured deadline,
so this is not a hard shutdown-time guarantee. Failed kill or wait can leave the
child alive; an exception is not proof of successful termination.

The retained original scalar decoder is the baseline. `production` invokes the
real installed/source decoder; `compiled_struct` is an independent prototype of
the selected mechanism. The comparison only informs this existing object ABI;
array-native downstream processing needs its own audit.

Evidence admission requires assertions enabled. `-O`, `-OO` and nonzero
`PYTHONOPTIMIZE` are rejected at module load, including helper imports: Python
optimization removes parity assertions and the handshake/warm-up calls inside
them. This guard does not establish the validity of historical timing reports or
complete the current component technology reassessment. Focused checks:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH=integrations/edge:tests/integration \
  python -m unittest test_sensor_packet_audit_modes
```

New reports include `source_sha256` for this harness, its worker and the actual
imported packet module's on-disk file. Labels are logical names, with no absolute
installation paths. Each case includes `fixture_sha256.payload` for its exact
bytes and `fixture_sha256.layout_json` for UTF-8 JSON with sorted keys, compact
separators and nonfinite values rejected. Hashing occurs outside timed samples.
Unreadable source files abort report generation instead of emitting incomplete
source bindings. These are on-disk fingerprints, not executable attestation,
authentication, a dependency closure or a race-free snapshot. Keep the installed
sources stable during a run. Historical reports are unchanged and are not
retroactively source-bound by this addition. See the
[partial source-binding review](../../../docs/engineering/aethron-ecosystem/P21-PACKET-SOURCE-EVIDENCE-V3.md).
