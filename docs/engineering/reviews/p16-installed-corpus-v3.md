# P16 installed behavioral corpus review v3

Baseline: `3c2f9786c4fe904b30acc2166b0873dd881a5d1d`, reviewed 2026-10-10.
Decision: **KEEP direct Python API checks; FIX silent loss of fixture coverage**.

The current parser, trust, evidence, task, bundle, federation and inbox implementation
was re-read before reviewing the installed-package workflow. Runtime contracts remain
unchanged. This correction concerns packaging evidence, not production admission.

## Demonstrated mismatch

The workflow's installed-consumer code iterated each fixture's `cases` without
requiring any cases. A bounded reproduction executed that exact inline Python body
and replaced one corpus at a time with an empty case list. All six executions returned
without error: one test method retained six expected-rejection assertion failures and
zero execution errors. Passing the step did not establish that all intended cases ran.

`scripts/passport_installed_vectors.py` now owns that same behavioral runner. The
workflow invokes it with `python -I`; its existing seven-module installed/source
comparison remains a preceding step. Six explicit SHA-256 pins and case counts bind
the reviewed fixture bytes: 4 inbox, 8 federation, 7 bundle, 7 task, 6 passport and
8 evidence cases. Empty, truncated, duplicated or modified corpora reject before their
loops. Pins require intentional review when fixture bytes change. Missing files fail.
The runner rejects optimized execution because its inherited behavioral assertions
must execute. JSON success output is emitted only after all 40 cases pass.

## Requirements and technology selection

This is an offline development/CI check of installed Python public APIs on the existing
Python 3.9/3.13 OS matrix. Inputs are six fixed, trusted repository fixtures; it is not
an untrusted file-ingest service. Requirements are direct API execution, preserved
negative outcomes, isolated source lookup and explicit coverage failure. There is no
target hardware deadline or measured runtime migration requirement.

| Candidate | Decisive property for this check |
|---|---|
| Python with standard unittest regression controls | [unittest](https://docs.python.org/3.13/library/unittest.html) supports direct API tests and expected-exception checks. The standalone driver preserves the existing installed API calls and adds explicit fixture validation. |
| pytest parametrization | [Parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html) organizes cases but has configurable handling of empty parameter sets. Coverage must still be explicitly required; parametrization alone is not the correction. |
| Java/Kotlin with JUnit | [JUnit](https://docs.junit.org/current/user-guide/) provides a separate JVM test ecosystem. Calling these Python APIs requires an additional process or language bridge; it does not independently establish that a Python fixture loop ran. A separate-language protocol consumer would answer a different interoperability question. |

KEEP the Python runner with explicit fixture pins: it exercises the installed API
directly without a newly introduced bridge or test plugin. This decision follows
the boundary being tested, not installed tooling, familiarity or rewrite cost. No
comparative speed ranking, hardware qualification or general language superiority
is asserted. Runtime choices for future transports and persistent services remain open.

## Verification and limits

Five new regression methods cover the valid run, 24 altered-corpus cases, a missing
file, incorrect verifier behavior and the optimization guard. The related suite has
91 passing methods and zero skips. Ruff and formatting pass; Bandit passes with B101
excluded for the runner's explicitly guarded assertions. Actionlint passes.

The existing installed copy matched all seven checked source modules. The isolated
runner then executed all 40 cases successfully, including from outside the checkout.
Real `-I -O` and `-I -OO` processes rejected with no JSON output. No new wheel build,
full clean clone, hosted CI run or release distribution was qualified here.

Fixture pins are reviewed-input identities, not signatures, author authentication,
complete mutation coverage or dependency attestation. These trusted files are read
wholly before hashing; this tool does not bound arbitrary hostile file reads. The
installed/source comparison and behavior run are separate processes, not atomic
loaded-code attestation. P17/P18/P19 deployment, MLS, CNSA and availability claims remain
unsupported. Insufficient information for tactical deployment.

```sh
PYTHONPATH=tests:. python -m unittest test_passport_installed_vectors test_passport_install_check -v
python -I scripts/passport_install_check.py
python -I scripts/passport_installed_vectors.py
```

[Evidence record](p16-installed-corpus-v3-results.json). Next earliest review boundary:
the consumed P2/P3/P14 contracts. No whole-lane audit completion marker is issued.
