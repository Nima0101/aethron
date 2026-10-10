# P1.1 synthetic build-backend comparison

The scoped backend decision is **KEEP Setuptools**, recorded in
[ADR0030](../decisions/0030-package-backend-review.json). These experiments compare
packaging contracts; they do not qualify either product package.
The root and edge packages both have optional native Cython build modes in their
`setup.py` files. Any proposed replacement must preserve those modes, the supported
Python/platform matrix, offline installation, resource inclusion and entry points.

The executable compares Setuptools 84.0.0, Hatchling 1.32.4, Flit Core 4.1.0 and
uv_build 0.13.0 using a tiny generated package. Each backend builds two wheels with
a fixed `SOURCE_DATE_EPOCH`; the probe checks byte equality within that backend,
metadata, GPL licence bytes, JSON/PXD resources, exclusion of an unrelated file,
and an installed console command outside the fixture directory. It never imports
or executes product code. The probe uses Python to invoke PEP 517 Python hooks,
inspect ZIP/metadata and create installation environments through their native
interfaces; the backend candidates include the Rust implementation in uv_build.
This fixture is not a comparison of arbitrary runtime languages.

On 2026-10-10, all four backends passed on Linux x86_64 / CPython 3.13.13.
Two wall-time samples per backend are diagnostic observations, not a performance
ranking. Cached state, concurrent load and this small fixture prevent a general
latency or memory conclusion. Repeated wheels on one host do not establish
cross-platform reproducibility. The version-specific lock is for this experiment,
not the product build or Python 3.9 support.

Run on Linux x86_64 with Python 3.13 and a pip supporting `--python`:

```sh
python -m pip install --only-binary=:all: --require-hashes --no-deps \
  --target build/backend-tools -r requirements-backend-probe-linux.lock
python -m unittest tests.test_backend_parity_probe -v
python scripts/backend_parity_probe.py --tools build/backend-tools \
  --out build/backend-proof
```

Use a new output directory for each run. `results.json` is incremental: a failed
run can leave partial results. Success requires process exit zero and the expected
candidate entries. Child operations have timeouts; there is no claim of total
memory, filesystem or hostile-code containment. Backends must be trusted and
hash-verified before execution. Optimized Python is rejected because assertions
are part of the probe's checks. The dedicated workflow retains only small logs,
fixtures, wheels and results, not installed environments.

Initial harness failures are retained in local review evidence: uv's executable
was missing from the isolated PATH; then ZIP directory entries were incorrectly
counted as payload files. Negative controls reproduce directory-entry acceptance,
missing/extra/changed resources, unrelated metadata directories, changed metadata,
licence/entry-point errors and rejection under optimized Python. These failures
were probe defects, not evidence that a candidate backend failed the contract.

The native comparison also rebuilds portable and Cython-compiled wheels from
small synthetic source archives. [Setuptools supports native extensions](https://setuptools.pypa.io/en/latest/userguide/ext_modules.html);
[uv_build currently supports pure Python](https://docs.astral.sh/uv/concepts/build-backend/).
[Hatch build configuration](https://hatch.pypa.io/latest/config/build/) and
[Flit project configuration](https://flit.pypa.io/en/stable/pyproject_toml.html)
define the other tested packaging boundaries. Native-oriented alternatives remain
eligible, including [meson-python](https://mesonbuild.com/meson-python/) and
[scikit-build-core](https://scikit-build-core.readthedocs.io/en/latest/).
The pure-Python fixture alone cannot justify the decision; the native experiment
and current build requirements support the limited KEEP. P1 is not complete.

Run the additional native experiment with GCC/Clang, Python development headers,
Git and CMake >=3.20 available:

```sh
python -m pip install --only-binary=:all: --require-hashes --no-deps \
  --target build/native-backend-tools -r requirements-native-backend-probe-linux.lock
python -m unittest tests.test_native_backend_probe -v
python scripts/native_backend_probe.py --tools build/native-backend-tools \
  --out build/native-backend-proof
```

Setuptools, Meson and scikit-build-core each passed portable and compiled cases
on the Linux host. Portable builds receive invalid CC/CXX paths; compiled imports
must resolve to an extension and preserve positive and negative `2**100` values.
Source archives must exclude the unrelated fixture file and preserve the inputs.
Initial scikit-build-core defaults tagged the portable wheel as platform-specific;
explicit `wheel.cmake=false` corrected the fixture. Multiple source roots and a
portable wheel with a native ABI tag are rejected by additional negative controls.

The native lock pins Python-distributed tools for CPython3.13/Linux x86_64. The
host compiler, Python headers, Git and CMake remain prerequisites, with versions
recorded in CI artifacts. This is not a hermetic toolchain or proof of native
byte reproducibility. `results.json` can be partial on failure; require exit zero
and all six expected cases. No product module is imported or executed.
