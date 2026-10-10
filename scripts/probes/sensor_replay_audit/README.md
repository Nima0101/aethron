# C02 bounded replay audit probes

From a Python environment containing the edge package and its pinned dependencies:

```sh
PYTHONPATH=integrations/edge python scripts/probes/sensor_replay_audit/compare.py
UV_THREADPOOL_SIZE=1 node --v8-pool-size=1 scripts/probes/sensor_replay_audit/json_candidate.cjs
```

No new Python dependency is needed. The comparison holds one synthetic 1 MiB
payload, uses a temporary file and 15 rotated samples for each I/O candidate.
CPU/wall timing excludes tracing; peak allocation is measured in separate calls.
An existing trace session is rejected before fixture creation and left intact.
Each trace session started by the harness is stopped if a candidate, peak read
or interrupt exits the allocation pass. This assumes exclusive process tracing
ownership during the run; it is not synchronization against another thread
starting or stopping tracing. Traced allocation is not total process memory.
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

New comparison reports include `source_sha256` for the harness and the actual
imported replay module's on-disk file, and `payload_sha256` for the complete
synthetic payload. Initial hashing occurs before temporary-file creation. The
same two captured paths are hashed again after fixture cleanup, before JSON
emission, outside measurement passes. A changed digest raises
`replay_audit_source_changed`; unreadable sources propagate their read errors.
Neither failure emits a JSON report. Labels omit
absolute paths. These fingerprints are not authentication, executable
attestation, a complete dependency closure or an atomic snapshot; run with stable
trusted sources. Matching before/after reads cannot detect files changed and
restored between reads, changes after the final read, or differences from code
already loaded in memory. The separate JSON counterexample probe is not executed by this
comparison and is not covered by its manifest. Historical reports remain
unchanged. See the [partial provenance review](../../../docs/engineering/aethron-ecosystem/P21-REPLAY-SOURCE-EVIDENCE-V3.md).
