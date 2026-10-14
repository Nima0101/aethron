"""Real child startup checks against foreign Python home and import paths."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class VerificationEnvironment(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    def test_children_remove_import_overrides_without_mutating_parent(self):
        for value in ("", "foreign interpreter path"):
            with (
                self.subTest(value=value),
                patch.dict(
                    os.environ,
                    {
                        "PYTHONHOME": value,
                        "PYTHONPATH": value,
                        "ORT_DISABLE_TELEMETRY": "0",
                        "AETHRON_TEST_ENV_SENTINEL": "preserved",
                    },
                ),
            ):
                inherited = dict(os.environ)
                with self.fixture("value = 1"), patch.object(verify.subprocess, "run") as child:
                    verify.run()
                self.assertEqual(child.call_count, 5)
                expected = dict(inherited, ORT_DISABLE_TELEMETRY="1")
                del expected["PYTHONHOME"], expected["PYTHONPATH"]
                for call in child.call_args_list:
                    self.assertEqual(call.kwargs["env"], expected)
                    self.assertIsNot(call.kwargs["env"], os.environ)
                self.assertEqual(dict(os.environ), inherited)

    def test_every_child_executes_despite_foreign_startup_and_home(self):
        invoke = subprocess.run
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory) / "foreign"
            foreign.mkdir()
            # A successful exit during startup must not replace a verification
            # child. This fixture can otherwise produce PASS without its body.
            (foreign / "sitecustomize.py").write_text("import os\nos._exit(0)\n", encoding="utf-8")
            (foreign / "foreign_probe.py").write_text("value = 1\n", encoding="utf-8")
            for home in (None, "", str(foreign), str(foreign / "missing")):
                with self.subTest(home=home), patch.dict(os.environ):
                    os.environ.pop("PYTHONHOME", None)
                    if home is not None:
                        os.environ["PYTHONHOME"] = home
                    os.environ["PYTHONPATH"] = str(foreign)
                    inherited = dict(os.environ)
                    results = []

                    def probe(args, results=results, **kwargs):
                        result = invoke(
                            [
                                sys.executable,
                                "-c",
                                "import importlib.util; "
                                "assert importlib.util.find_spec('foreign_probe') is None; "
                                "from aethron.example import value; "
                                "assert value == 1; print('check_body_executed')",
                            ],
                            cwd=kwargs["cwd"],
                            env=kwargs["env"],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=5,
                        )
                        results.append(result)
                        return result

                    with (
                        self.fixture("value = 1") as (output, _),
                        patch.object(verify.subprocess, "run", side_effect=probe),
                    ):
                        verify.run()
                    self.assertEqual(dict(os.environ), inherited)
                    self.assertIn("PASS:", output.getvalue())
                    self.assertEqual(len(results), 5)
                    for stage, result in enumerate(results):
                        with self.subTest(stage=stage):
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertEqual(result.stdout.strip(), "check_body_executed")
