# P16 installed-package evidence review v3

Baseline: `74931e5a9dd58f6113a6dbe6f76aeab64ebab02d`. Reviewed 2026-10-10.
Decision: **KEEP standard wheel packaging; FIX installed-source evidence gap**.
No runtime module, wire contract, signed fixture or acceptance rule changes.

## Constraints and technology reassessment

This component checks developer-built Python distributions on Linux, macOS and Windows,
with Python 3.9 and 3.13 in the hosted matrix. It must distinguish a regular installation
from checkout imports and detect stale installed source, even when behavior on a small
vector corpus is unchanged. Inputs are trusted repository/build files, not external
messages. There is no real-time deadline or physical target qualification here.

| Candidate | Evidence and decision |
|---|---|
| Setuptools / standard wheel | [Package discovery](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html) supports explicit package inclusion. The current `aethron*` selection includes the seven checked files, confirmed by a local wheel/install check. KEEP for this slice; no custom backend is needed. |
| Hatchling | [Build selection](https://hatch.pypa.io/latest/config/build/) provides explicit includes/excludes and reproducible-build configuration. Credible for the same distribution. It does not by itself establish which files the consumer interpreter imported. No requirement-derived advantage warrants a package-wide migration here. |
| Rust / Maturin | [Maturin](https://www.maturin.rs/) supports Rust-backed Python distribution. Appropriate to reassess if a component decision selects a native Rust extension; this evidence checker performs no native computation requiring that path. |
| Meson / meson-python | [Meson backend](https://mesonbuild.com/meson-python/) supports native extensions in multiple compiled languages, including D and Fortran. Credible for future compiled components; no native compilation or ABI requirement exists for this check. |
| Python standard-library checker | [Isolated mode](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I) excludes the script directory and user site and ignores Python environment variables. Direct inspection in the tested interpreter provides its import locations without a second runtime or custom interpreter-path model. SELECT. |
| JavaScript / Node orchestration | [Child processes](https://nodejs.org/api/child_process.html) can invoke the tested interpreter. Credible for a wider multi-runtime harness; this narrow check would still need to inspect Python import locations. An extra orchestrator supplies no additional evidence for this requirement. |

These decisions follow the artifact/import boundary, not installed-tool convenience,
language familiarity or rewrite cost. No speed ranking or universal backend preference
is claimed. Package-wide configuration and other lanes' packaging checks are unchanged.

## Gap and correction

The workflow already used a regular installation and isolated vector execution.
[pip distinguishes regular and editable installs](https://pip.pypa.io/en/stable/topics/local-project-installs/).
However, the workflow did not compare imported P16 files with reviewed source. Finite
behavior tests alone cannot detect every stale build: adding a comment changes the
artifact without changing its behavior.

`scripts/passport_install_check.py` now requires isolated execution, resolves the imported
file locations, rejects locations within the checkout, and compares bytes for the six
P16 runtime modules and the consumed JSON-bound helper. It prints source digests only
after every comparison succeeds. The workflow runs this before its behavior tests and
includes checker changes in both path filters.

Five focused tests use real temporary files: one identical-copy positive and four
negative controls covering changed bytes, direct source import, another file under the
source tree, and a missing installed file. The four negatives failed against the empty
checker and passed after implementation. Running the CLI without `-I` exits nonzero.
A fresh 76,868-byte wheel was built without downloads, installed into the existing lane
test environment, and all seven file comparisons passed. Isolated test discovery then
passed 46 passport/tooling tests and 43 interop tests with no skips.

## Limits and remaining inventory

This is a trusted-build consistency check, not authentication of an untrusted wheel.
Importing a package executes code before this check; it is not a sandbox. File equality
does not authenticate the checkout, validate loaded bytecode, check every transitive
dependency, establish reproducible wheel bytes or attest an entire distribution. The
schemas and portable fixtures are repository tooling inputs, not claimed wheel resources.
Existing environment reuse is not a clean-environment or clean-clone result. Hosted
execution of this correction remains pending; local Linux success is not a macOS or
Windows result. No MLS, CNSA, availability or physical timing claim follows.

The six P16 runtime modules and their conformance tooling have individual review records.
P16 transport/cross-phase completion and the declared P17/P18 software scope still need
an explicit inventory review. The presence of plans is not implementation evidence.
No whole-lane audit-complete marker is justified. Next: remaining phase inventory and
qualification-claim review, with unsafe operational subcomponents excluded separately.

Hashes, wheel identity and focused outcomes are retained in
[the result record](p16-packaging-v3-results.json). Reproduce after a regular installation:

```sh
python -I scripts/passport_install_check.py
python -I -m unittest discover -s tests -p 'test_passport*.py'
python -I -m unittest discover -s tests -p 'test_interop*.py'
```
