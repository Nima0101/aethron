# P1.1 synthetic build-backend comparison

The package backend decision remains **OPEN**. This experiment compares packaging
contracts; it does not qualify either product package or select a winner.
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

Next compare optional native-extension builds and source distributions using
small synthetic inputs. [Setuptools supports native extensions](https://setuptools.pypa.io/en/latest/userguide/ext_modules.html);
[uv_build currently supports pure Python](https://docs.astral.sh/uv/concepts/build-backend/).
[Hatch build configuration](https://hatch.pypa.io/latest/config/build/) and
[Flit project configuration](https://flit.pypa.io/en/stable/pyproject_toml.html)
define the other tested packaging boundaries. Native-oriented alternatives remain
eligible, including [meson-python](https://mesonbuild.com/meson-python/) and
[scikit-build-core](https://scikit-build-core.readthedocs.io/en/latest/).
No KEEP/MIGRATE decision or P1 completion follows from the pure-Python fixture.
