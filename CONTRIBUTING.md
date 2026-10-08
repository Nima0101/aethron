# Contributing
Read [AGENTS.md](AGENTS.md), the [active safety amendment](docs/safety/amendment-v3.md) and [protocol 3](docs/architecture/protocol-v3.md). Frozen history must remain inspectable. Open a concrete bug report with synthetic reproduction and observed/expected output. Never attach real human imagery, identifiers, precise behind-wall data or secrets.

Run `python3 scripts/verify.py`. Security, parser, fusion, model and visualization changes need negative tests before fixes; add a regression for every semantic defect. Install development tools in an isolated environment with `python3.13 -m venv .venv` then `.venv/bin/python -m pip install -r requirements-dev.txt`. Run Ruff check/format, Bandit, coverage, 60-second fuzz and dependency audit as documented in [verification](docs/verification/README.md).

Do not call same-author review independent assurance. Do not weaken gates, reuse person identifiers, add telemetry, train on evaluation data or claim synthetic evidence as hardware validation. Changes to current safety scope require explicit owner authorization and a public versioned amendment. Contributions are under Apache-2.0; preserve provenance and notices.
