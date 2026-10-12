# Qualification declaration harness verification

This is software-only evidence. Artifact authenticity, exact-device performance,
field/domain qualification and independent certification remain unverified.

## Retained test development evidence — 2026-10-09

The initial 12 feature tests failed before the validator existed. A subsequent
CLI privacy regression reproduced argparse echoing an invalid argument; the
entry point now emits only `invalid_qualification_manifest`. All 14 focused
tests then passed on Python 3.9.6 and 3.13.15. Ruff 0.16.10 lint/format and Bandit
passed. Neither run exercised hardware.

The expired-calibration fixture deliberately remains a failing declaration. Its
calibration expires one millisecond before capture end and its report retains
`calibration_interval`; exit 1 is expected. The synthetic complete fixture exits
0 but never sets artifact verification or physical qualification to true.

## Linux continuation — 2026-10-10

The migrated harness passes all 14 focused tests on Python 3.13.5. Ruff 0.16.10
lint/format and Bandit 1.9.4 pass, with no production-code security findings.
Both fixture reports reproduce twice byte-for-byte with their expected exit
codes; all 80 existing frozen file bindings remain unchanged. Full repository
verification, temporal evaluation, long fuzz, packaging, clean clone and soak
were not run in this focused lane. These results do not replace those gates.
The dedicated workflow is provided for hosted execution; a hosted pass is not
claimed by this document.
