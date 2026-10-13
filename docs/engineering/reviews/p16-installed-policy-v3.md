# P16 installed policy API coverage review

Reviewed 2026-10-10 against `76704946d2a518d211dd5f652146dcf73c5e5ba9`.
Decision: **KEEP direct isolated Python conformance; FIX missing policy API cases**.
This is generic software packaging assurance, not operational qualification.

## Review boundary and mismatch

The earliest parser, canonicalization and policy implementation were re-read, including
complete field validation, exact-byte policy pins and caller-supplied floors. This
slice changes no production API, policy rule or frozen threshold. Older component
reviews remain evidence inputs; this record does not complete the lane re-audit.

The installed runner covered six corpora and 40 cases but never called
`validate_pinned_policy`. Source-tree unit tests therefore did not establish installed
API coverage. The existing local installation was demonstrably stale: the source check
rejected `installed_source_mismatch`, and the updated runner failed to import the API.
Both failures are retained, independently of the subsequent successful installation.

## Constraints and technology reassessment

The boundary is a small trusted offline fixture corpus against the actual public
Python wheel API. It needs exact rejection/metadata comparisons, external installed
imports and no service, hardware, real-time scheduling or throughput target. JSON
with hex-encoded input bytes preserves malformed UTF-8 and lexical duplicate fields.

| Candidate | Decisive property and decision |
|---|---|
| Direct Python script and unittest | `python -I` excludes script-directory and user-site imports and ignores Python environment variables. Direct calls inspect the actual wheel API and its complete return fields without an additional serialization adapter. KEEP with the separate installed-source check. [Python documentation](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I). |
| pytest | Provides installed-package testing patterns and import-mode controls. Credible when richer discovery/fixtures are needed; neither supplies the missing policy cases automatically. No such additional requirement in this bounded script. [Integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html). |
| Robot Framework keyword language | An acceptance-test alternative using libraries and keywords. It would require a Python library boundary for these return objects; operator-readable scenario authoring is not needed for this low-level corpus. [User guide](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html). |
| CMake/CTest scripting | Can drive subprocess tests, expose exit failures and publish structured results. It could orchestrate the same Python check but cannot replace inspection of the installed Python objects. No compiled-build orchestration requirement here. [CTest manual](https://cmake.org/cmake/help/latest/manual/ctest.1.html). |
| Java/Kotlin with JUnit | Credible independent JVM test ecosystem. A subprocess or bridge would still be needed for this API, adding a serialization boundary without a new qualification property. [JUnit guide](https://docs.junit.org/current/user-guide/). |

These are constraint-based conclusions, not measured speed rankings. Python's
incumbency, local tool availability and rewrite cost are not the deciding properties.
The portable byte corpus remains reusable by future implementations. No runtime
migration is justified by this packaging-only comparison.

## Executable correction and retained outcomes

Ten pinned cases add exact and pretty policy bytes, a wrong pin, clock/revision
rollback, expiry/pre-issue boundaries, an unknown field, invalid UTF-8 and a duplicate
field. Expected status, reason and all three metadata fields are explicit fixture
values. The runner also requires all three non-authorizing flags to remain false.

The initial seven-method runner test produced ten assertion failures, with no errors:
missing corpus, total-count shortfall, and eight undetected result-field changes.
After implementation, a test helper using `vars()` omitted dataclass defaults, causing
two errors. It now uses `dataclasses.asdict()`; that intermediate failure remains in
local evidence. Ruff also caught two loop-variable binding findings; the helper now
binds the selected field/value explicitly. No production defect is claimed.

Twenty related methods pass without skips. The existing corruption test now covers
seven corpora and 28 altered-corpus cases. Eight injected incorrect result fields are
detected. Ruff and formatting pass. Unfiltered Bandit reports 24 low-severity B101
assertion-use findings. The explicit B101-excluded scan passes; this is not an
unqualified clean scan. Real isolated `-O` and `-OO` invocations each reject with
`optimized_execution_not_supported`, emit no JSON result and return nonzero.

A 77,429-byte portable wheel was built offline with no dependencies/build isolation
using the declared setuptools 84.0.0 and wheel 0.48.0. It was reinstalled into the
existing lane virtual environment. The seven-module external-source identity check
passes, followed by 50 installed behavioral cases. The build/install cache-permission
warning is retained; neither command required privileged access or downloads.

Reproduce in a suitable prepared environment:

```sh
PYTHONPATH=tests:. python -m unittest test_passport_installed_vectors test_passport_install_check test_passport_policy -v
python -m pip wheel --no-index --no-deps --no-build-isolation --wheel-dir /tmp/p16-wheel .
python -m pip install --no-index --no-deps --force-reinstall /tmp/p16-wheel/aethron-0.2.0-py3-none-any.whl
python -I scripts/passport_install_check.py
python -I scripts/passport_installed_vectors.py
```

The existing workflow already selects the runner, tests and fixture directories; no
workflow change is necessary. This local run is not hosted CI, a clean-environment
install, reproducible distribution proof, complete dependency attestation or customer
acceptance. Fixtures/scripts are repository tooling, not claimed wheel resources.
Isolated Python and source-byte comparison do not sandbox an untrusted wheel or attest
loaded bytecode. No hardware, MLS, CNSA, uptime or tactical claim follows.

[Source/log digests and outcomes](p16-installed-policy-v3-results.json) bind the listed
inputs only, not an atomic whole-environment snapshot. Next: inspect the generic
installed-evidence report's source/dependency boundaries; the full re-audit remains open.
