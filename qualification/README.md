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
Supply exactly one `--now-ms INTEGER` or `--now-ms=INTEGER`; repeated or
abbreviated time options are rejected with exit 2, including repeated identical
values. This prevents an appended option from silently replacing the instant.
The stdin byte limit bounds admission size, not how long a pipe may take to
produce input; callers own process supervision and input/output deadlines.
The command flushes its report before returning a declaration status. Its `main()`
maps write/flush errors to status 2 and the fixed diagnostic when stderr is writable.
Output is not atomic: a failed write or flush can leave partial or complete JSON.
Consumers must check process status and parse a complete report. Module execution
closes process-owned stdout after status 2, preserving the fixed failure for the
tested closed-pipe path instead of retrying its buffered flush during shutdown.
Direct calls to `main()` leave caller-owned streams open. Failed stderr or other
interpreter teardown failures can still alter final status or diagnostics;
flushing is not durable storage or downstream acknowledgement. See the historical
[output boundary review](technology/report-output-review-v3.md) and the
[process shutdown correction](technology/cli-shutdown-review-v3.md).

Reports contain the input SHA-256 and aggregate counts, not rig/sensor IDs,
device digests, timestamps, measurements or input error text. The input digest
is linkable and is not anonymization. Do not put personal information or private
device identifiers in manifests intended for publication. Evidence references
are declarations, never proof that the referenced bytes exist or are authentic.

The versioned contract is [schema-v1.md](schema-v1.md). The included rig is
entirely synthetic; its repeated-digit hashes are placeholders, not hardware
evidence. Environment validation currently covers lighting declarations only.
Software schemas and evidence checks for power, weather, temperature, vibration
and EMC are not implemented here; they remain software work. Actual instrument
measurements, representative field accuracy and independent privacy, safety and
certification review remain external gates. Missing software is not an external
qualification gate; see the [readiness inventory](p15-readiness-v1.md).

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

[P15 capture campaigns](campaign-v1.md) compare a bounded caller-supplied matrix
with minimized capture declarations. The API retains failed attempts and rejects
exact duplicate captures; its report binds both the plan and submitted inputs.
It measures declaration coverage, never physical sample independence or field
qualification, and cannot prove preregistration or detect attempts omitted by
the caller. The included plan and inputs below are synthetic:

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

The separate [campaign reference byte checker](campaign-references-v1.md) matches
supplied domain/procedure bytes to the plan's hashes. It does not authenticate
those references, approve their contents or change campaign qualification flags.
The separate [procedure checklist API](procedures-v1.md) checks strict, bounded
case/check declarations against the same plan and preserves missing, unknown and
unverified states. It runs no procedure and does not validate referenced method
contents or human approval. [Synthetic vectors](fixtures/procedures-v1.json)
include complete-but-unverified, unknown, missing and conflicting declarations.
The [domain declaration API](domains-v1.md) compares whole lighting/sensor/evidence
profiles with campaign cases in both directions. Null fields never act as
wildcards, and matching columns separately cannot invent a supported combination.
Its [synthetic vectors](fixtures/domains-v1.json) retain unknown, empty and joint
mismatch cases. These checks do not establish field suitability or domain approval.
The [method-reference verifier](methods-v1.md) binds caller-supplied method bytes
to checklist references and checks declarations of the frozen software rules.
It preserves checklist, byte and content failures independently. It executes no
procedure and does not approve physical methods; [synthetic vectors](fixtures/methods-v1.json)
retain unknown-rule, changed-rule, missing and corrupt evidence outcomes.
The [campaign bundle report](campaign-bundle-v1.md) computes both coverage and
reference matching from raw inputs against one plan. Its software result requires
both checks; capture artifact verification and physical qualification remain false.
The [stdin bundle command](campaign-bundle-stream-v1.md) accepts one bounded binary
frame, preserves original evidence bytes, and emits the same report with exit 0/1/2.
The [portable synthetic vectors](consumer-vectors-v1.md) reproduce six consumer
outcomes without Python fixture builders. The [P4/P15 readiness inventory](p15-readiness-v1.md)
separates implemented checks, unfinished software and external qualification gates.

## Technology decision and execution plan

The [current declaration review](technology/review-v3.md) records deployment
constraints, technology alternatives, executable evidence and limitations. The
earlier [policy-2 experiments](technology/retrospective-v2.md) remain evidence,
not completion of the current review. A language is not excluded because it
requires compilation. No generic JSON Schema conformance is claimed.
The [source coverage checkpoint](technology/coverage-review-v3.md) maps the
implemented components to decisions and current source observations. It does
not mark P4/P15 or customer acceptance complete.

Declaration success is not live sensor admission. Record age is assessed at
capture end, and capture age at the supplied evaluation instant; those separate
100 ms windows can total 200 ms. The v1 input hash binds manifest bytes only,
not that evaluation instant. A reviewer must retain the supplied instant and
its clock-domain provenance separately. The digest neither authenticates an
instrument nor establishes access-control, encryption or certification claims.

Implementation uses `qualification/evidence.py` for parsing/reporting,
`qualification/__main__.py` for bounded stdin, and `qualification/tests/` for
independent synthetic and negative cases. First observe failing tests, implement
the contract, then run focused tests, lint/security and deterministic CLI replay.
Use no local full matrix, long fuzz, VM or soak. Do not alter frozen protocols.
Deliver through the assigned branch and protected-main PR when Git permissions
allow; do not bypass required hosted checks.

The [software assessment API](assessment-v1.md) now composes domain, method,
campaign and per-capture artifact checks from raw inputs. Its aggregate result
is software consistency only; authentication, independent review and physical
qualification remain unverified. Existing bundle/stream v1 reports are unchanged.
