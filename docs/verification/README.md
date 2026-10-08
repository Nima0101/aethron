# Verification
Current [v3 gates](matrix-v3.md), [results](status-v3.md) and [safety review](../safety/review-v3.md) extend all earlier checks. Run `python3 scripts/temporal_evaluate.py --out build/v3-registered`, `python3 scripts/temporal_fuzz.py`, the optional model E2E and README artifact reproduction in addition to the commands below.

Core check: `python3 scripts/verify.py` (Python 3.9+, standard library). Tests include 2,400 deterministic generated fusion/reference/permutation/withdrawal trials, v1 boundaries, darkness and the seven required v2 human-envelope cases. No tests intentionally skipped.

Full candidate checks:

```sh
.venv/bin/ruff check aethron tests scripts
.venv/bin/ruff format --check aethron tests scripts
.venv/bin/bandit -r aethron
.venv/bin/coverage run --source=aethron -m unittest discover -s tests
.venv/bin/coverage report -m
.venv/bin/pip-audit --cache-dir build/audit-cache --disable-pip --no-deps -r requirements-dev.txt
python3 scripts/fuzz.py
python3 scripts/reproduce.py
```

Fuzz duration is fixed at 60 seconds; execution count is measured. Do not substitute a shorter smoke for the frozen gate. Reproduction requires committed clean source and Git; it clones locally, executes README commands, imports the packaged library outside the checkout and compares two builds byte-for-byte. Python timing is not hard-real-time evidence. Static checks are bounded analysis, not an audit certificate.

[Original matrix](matrix.md), [darkness matrix](darkness-matrix.md), [v2 matrix](amendment-v2-matrix.md), [gate status](status.md), [hardware blockers](hardware.md), [failure log](failure-log.md).

Wheel reproducibility/install check: `.venv/bin/python scripts/package_check.py` (development Python 3.10+, tested 3.13). Real-browser check: `.venv/bin/python scripts/browser_check.py` requires a permitted Chromium environment; blocked locally, not skipped into a pass. Runtime/zipapp quickstart remains Python 3.9+.
