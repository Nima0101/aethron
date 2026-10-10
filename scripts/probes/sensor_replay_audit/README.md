# C02 bounded replay audit probes

From a Python environment containing the edge package and its pinned dependencies:

```sh
PYTHONPATH=integrations/edge python scripts/probes/sensor_replay_audit/compare.py
UV_THREADPOOL_SIZE=1 node --v8-pool-size=1 scripts/probes/sensor_replay_audit/json_candidate.cjs
```

No new Python dependency is needed. The comparison holds one synthetic 1 MiB
payload, uses a temporary file and 15 rotated samples for each I/O candidate.
CPU/wall timing excludes tracing; peak allocation is measured in separate calls.
The fragmented stream caps reads at 4096 bytes. All returned bytes must match.
The readinto prototype assumes that optional stream interface and is not a full
replacement for the production reader's EOF/adapter contract.

`json_candidate.cjs` is a bounded counterexample probe for stock JSON.parse,
not a complete Node replay implementation. It preserves duplicate/escaped-key
and integer-precision failures. It does not establish that a properly configured
alternative parser cannot implement the contract. No live input or network is
used. No benchmark is a hardware or real-time qualification result.

The comparison requires assertions enabled. Optimized execution/import (`-O`,
`-OO`, or nonzero `PYTHONOPTIMIZE`) is rejected because it removes byte-equality
checks from both timing and allocation passes. Focused evidence-admission tests:

```sh
PYTHONPATH=integrations/edge:tests/integration \
  python -m unittest test_sensor_replay_audit_modes
```

These tests deliberately fail the first candidate in each measurement pass and
require no report output. They do not rerun the performance matrix or requalify
historical reports. The full current technology reassessment remains incomplete.
