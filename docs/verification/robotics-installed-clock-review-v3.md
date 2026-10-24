# Installed clock-withdrawal verification

This is a focused continuation of the [clock correction](robotics-clock-withdrawal-review-v3.json),
not a product acceptance run. The earlier missing-package and missing-Pydantic
errors remain recorded. At source commit `063c8d7ebea65639e25a2f9fb6b6a25a15555fac`,
the local environment was completed without changing tests or production code.

The five Pydantic requirements were selected unchanged from
`integrations/edge/requirements-server.lock`: annotated-types, pydantic,
pydantic_core, typing_extensions and typing-inspection. Installation required
binary wheels and the existing hashes. Build tools were version-pinned to
setuptools 84.0.0, wheel 0.48.0 and packaging 26.3 from official PyPI; this build-tool
installation was not hash-locked. No source dependency build or privileged install
was used. The existing virtual environment already held the locked MAVLink SDK.

One portable wheel per local project was built with pip wheel, `--no-deps`,
`--no-build-isolation`, `--no-cache-dir`, `SOURCE_DATE_EPOCH=1767225600`, and both
`AETHRON_BUILD_NATIVE_BOUNDS=0` and `AETHRON_BUILD_NATIVE_CLOCK=0`. Both wheels
were installed with `--no-index --no-deps` from the retained local output. Pip's
dependency check then passed. Artifact sizes, hashes and a selected wheel-member
hash are retained in the [receipt](robotics-installed-clock-review-v3.json).
There was no second build, clean clone, fresh virtual environment, release signing,
full package matrix or independent customer installation.

Save the following exact runner as `check.py` outside the checkout. Run it with
`/path/to/installed-venv/bin/python -I check.py /path/to/source-checkout` after the
above packages are installed. It reads test fixtures from the supplied checkout,
but imports the four checked production modules from the virtual environment and
requires byte equality with that checkout. Python documents the import exclusions
of [isolated mode](https://docs.python.org/3/using/cmdline.html#cmdoption-I).
This is Python test execution and module-origin inspection; running it in a foreign
runtime would still require embedding the interpreter. It does not decide the
production receiver's language.

```python
import hashlib
import json
import sys
import unittest
from importlib import import_module
from pathlib import Path

root = Path(sys.argv[1])
modules = {}
for name in ("mavlink", "signing", "boot_authority", "datagram_v1"):
    module = import_module("aethron_edge.telemetry." + name)
    path = Path(module.__file__).resolve()
    installed = path.relative_to(Path(sys.prefix).resolve())
    source = root / "integrations/edge/aethron_edge/telemetry" / (name + ".py")
    assert path.read_bytes() == source.read_bytes(), name
    modules[name] = {
        "installed_path": str(installed),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
print(json.dumps({"isolated": bool(sys.flags.isolated), "modules": modules}, indent=2), flush=True)
assert sys.flags.isolated
suite = unittest.TestSuite()
loader = unittest.TestLoader()
for name in (
    "test_telemetry",
    "test_signing",
    "test_clock_guard",
    "test_datagram_v1",
    "test_lifecycle_audit_v2",
):
    suite.addTests(loader.discover(str(root / "tests/mavlink"), pattern=name + ".py"))
result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
```

The formatted runner passed 68 tests in 2.378 seconds with no failures, errors or
skips; its earlier formatting-only variant passed the same 68 in 3.877 seconds.
Eight boot-clock methods also passed separately after dependency installation.
All four checked modules loaded below the virtual environment's site-packages,
including the corrected passive receiver. This resolves the two local setup
errors for this focused run. It does not re-audit all signing/boot logic or prove
clock accuracy, hard-real-time behavior, hardware support or runtime superiority.
Historical evidence is immutable, and the earliest-component technology decision
and the full lane review remain open.
