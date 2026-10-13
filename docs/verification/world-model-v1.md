# World-model v1 focused verification

Scope: P6 in-process boundary, additive to frozen v3. Software/synthetic evidence
only. No hardware, physical-frame, field-accuracy or production qualification.

## Retained red cases

Before implementation, `test_world.py` failed to import `aethron.world` with
`ModuleNotFoundError`, confirming the missing boundary.

After the first implementation, the added
`test_quarantine_keeps_known_negative_evidence_bounded` failed with
`AssertionError: 'rgb:dark' not found in ['clock_regression']`.
Reproduction: accept a dark RGB sensor report, reject a map-frame update, then
receive regressed watchdog time. Replacing diagnostics erased the known sensor
failure. The correction unions fixed diagnostic codes until a valid newer frame
replaces them. The test also checks repeated rejection cannot grow the set.

## Focused results

- `python3 -m unittest discover -s tests -p 'test_world*.py' -v`:
  18 PASS on Python 3.9.6, 18 PASS on Python 3.13.
- `python3 -m unittest discover -s tests -p test_temporal.py -v`:
  all 21 existing temporal tests PASS on Python 3.9.6.
- The new simulation suite reads frozen `data/temporal/*.json` and compares
  canonicalized scene outputs with direct Session use, including all fields
  except random IDs renamed by first occurrence inside the test only.
- Additional tests cover frame/clock quarantine, preserved watermarks, stale/future
  frames, camera/scene/evidence separation, capacity/rotation, blackout fusion,
  all-support loss, expiry/re-entry, range disagreement, calibration/registration,
  skew, detached outputs, close, privacy fields and 68 bounded malformed payloads.
- Focused syntax/whitespace and documentation-link checks PASS. All nine existing
  freeze manifests match their file hashes. No frozen document or threshold changed.
- Ruff 0.16.10 `check` and `format --check` PASS for `aethron/world.py` and both
  new test files. The initial check caught C408 (test helper used `dict()` instead
  of a literal); the helper was corrected and the focused checks rerun.
- Bandit 1.9.4 `-q aethron/world.py`: PASS, no findings. This is a focused static
  scan, not an independent security audit. An early attempt before installation
  completed reported the missing module; the completed pinned installation was
  used for the successful run. Runtime dependencies remain unchanged.

## Diagnostic performance — not a T10 pass

One local diagnostic compared 20 frames with four objects against direct Session
use on Python 3.9.6, Darwin arm64. Latency was measured without tracing; a separate
pass measured traced memory. These are small, uncontrolled local measurements,
not the frozen 100-frame/32-object T10 benchmark or hardware deadlines.

| Path | p50 ms | p95 ms | max ms | Peak traced bytes |
| --- | ---: | ---: | ---: | ---: |
| Direct Session | 2.725 | 228.478 | 230.424 | 14949 |
| WorldModel | 2.211 | 159.760 | 281.029 | 19768 |

Both diagnostic p95 values exceed 100ms. No timing pass or speedup is claimed;
the sample does not establish the cause of the long tails. Raw local results are
retained in `build/p6-world/diagnostic.json`. Thresholds were not adjusted.

## Delivery and unrun gates

The lane's fast-loop policy excludes local full repository verification, full
fuzzing, clean clone, VM/container, and full publication-matrix runs. Those gates,
packaging/reproduction and exact-head hosted checks remain required before a
merge or publication qualification. Existing CI discovers these tests through
the normal unittest discovery path; workflow existence is not a hosted PASS.

The original development environment denied Git fetch and staging because shared
Git metadata was outside its writable roots. That delivery failure is retained;
it did not invalidate the software tests or authorize bypassing the sandbox.

## Linux continuation — 2026-10-10

The migrated lane fast-forwarded to protected main `0ce84bf` without conflicts.
Focused verification on Python 3.13.5: all 18 world-model tests and all 21 temporal
tests PASS. Ruff 0.16.10 check/format and Bandit 1.9.4 pass on the changed Python
files; the seven-file public-content/link scan and all nine freeze manifests also
pass. The retired environment's timing measurements above remain negative
evidence; moving hosts does not turn them into a performance qualification.

The scope of this change is still the P6 boundary. Simulation-only defensive
interfaces, planning decisions, scenarios and multi-node coordination require
their own versioned contracts and focused evidence in subsequent changes.
