# P4 qualification evidence harness v1

This offline development harness checks declarations for one rig and one capture
interval. It never approves physical qualification, field performance, hardware
support or certification. It does not load referenced artifacts, authenticate
instruments, infer absence from missing evidence or change runtime admission.

Run from the source checkout with Python 3.9+:

```sh
python -m qualification --now-ms 1050 < qualification/rigs/synthetic-v1.json
python -m unittest discover -s qualification/tests -v
```

Exit 0 means declaration checks passed; physical qualification remains blocked.
Exit 1 retains sorted findings for a structurally valid but inconsistent,
missing or stale declaration. Exit 2 emits a fixed error on stderr and no report
for malformed input. `now_ms` is a separately supplied non-boolean monotonic
integer in the capture's clock domain; for replay the caller supplies the frozen
evaluation instant. It is not wall time or proof of a trustworthy clock.

Reports contain the input SHA-256 and aggregate counts, not rig/sensor IDs,
device digests, timestamps, measurements or input error text. The input digest
is linkable and is not anonymization. Do not put personal information or private
device identifiers in manifests intended for publication. Evidence references
are declarations, never proof that the referenced bytes exist or are authentic.

The versioned contract is [schema-v1.md](schema-v1.md). The included rig is
entirely synthetic; its repeated-digit hashes are placeholders, not hardware
evidence. Environment validation currently covers lighting declarations only;
power, weather, temperature, vibration, EMC, field accuracy and independent
privacy/safety/certification review remain external pending work.

`rigs/expired-calibration-v1.json` retains the negative case where calibration
expires one millisecond before capture end. Its CLI exit must be 1, with
`calibration_interval` in the report. Exact-byte expected reports for both rigs
are in `evidence/`; neither report verifies the placeholder artifact references.
The focused qualification workflow tests Python 3.9/3.13 and reproduces the
positive report. Workflow presence does not establish a hosted pass.
The [verification record](evidence/verification-v1.md) preserves local results
and the original negative cases without making physical qualification claims.

For caller-supplied evidence bytes, use the separate
[artifact byte-binding API](artifacts-v1.md):

```python
from qualification.artifacts import verify

report = verify(manifest_bytes, {artifact_sha256: artifact_bytes}, now_ms=1050)
```

The caller supplies every distinct referenced artifact. Matching hashes can
establish byte binding while calibration remains expired; inspect both
`artifact_bytes_verified` and `software_checks_passed`. Authentication and
physical qualification remain false. This bounded API opens no files/devices
and does not reinterpret the original declaration CLI's exit or report fields.

[P15 capture campaigns](campaign-v1.md) compare a bounded preregistered matrix
with minimized capture declarations. The API retains failed attempts and rejects
exact duplicate captures; its report binds both the plan and submitted inputs.
It measures declaration coverage, never physical sample independence or field
qualification. The included plan and inputs below are synthetic:

```python
from pathlib import Path
from qualification.campaign import evaluate

report = evaluate(
    Path("qualification/plans/synthetic-campaign-v1.json").read_bytes(),
    [
        {
            "case_id": "blackout",
            "manifest": Path("qualification/rigs/synthetic-v1.json").read_bytes(),
            "now_ms": 1050,
        }
    ],
)
```

## Technology decision and execution plan

Requirements: portable offline execution, bounded untrusted JSON, duplicate-key
rejection, exact scalar types, cross-record rig/time binding and zero additional
runtime dependencies. The [Python JSON documentation](https://docs.python.org/3.13/library/json.html)
provides duplicate-pair and nonfinite hooks; explicit byte/depth limits are still
needed. [JSON Schema object validation](https://json-schema.org/understanding-json-schema/reference/object)
can reject extra properties but needs separate cross-record logic. A compiled
Rust parser is another option but adds a build step without a demonstrated
throughput requirement for a 64 KiB offline document. Choose Python standard
library with an explicit versioned schema and semantic checks. Sources reviewed
2026-10-09. No generic JSON Schema conformance is claimed.

Implementation uses `qualification/evidence.py` for parsing/reporting,
`qualification/__main__.py` for bounded stdin, and `qualification/tests/` for
independent synthetic and negative cases. First observe failing tests, implement
the contract, then run focused tests, lint/security and deterministic CLI replay.
Use no local full matrix, long fuzz, VM or soak. Do not alter frozen protocols.
Deliver through the assigned branch and protected-main PR when Git permissions
allow; do not bypass required hosted checks.
