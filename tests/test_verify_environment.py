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

    def test_user_site_hooks_cannot_skip_children_or_hide_failures(self):
        # Base Python exercises startup even when the test runner uses a venv.
        python = getattr(sys, "_base_executable", sys.executable)
        invoke = subprocess.run
        for hook in ("sitecustomize.py", "usercustomize.py", "probe.pth"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env = dict(os.environ, PYTHONUSERBASE=str(root / "user-base"))
                for name in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE"):
                    env.pop(name, None)
                site = Path(
                    subprocess.check_output(
                        [python, "-S", "-c", "import site; print(site.getusersitepackages())"],
                        env=env,
                        text=True,
                        timeout=10,
                    ).strip()
                )
                site.relative_to(root)
                site.mkdir(parents=True)
                (site / hook).write_text("import os; os._exit(0)\n", encoding="utf-8")
                control = invoke(
                    [python, "-c", "print('executed')"],
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(control.stdout, "", "negative control must execute the hook")
                # Exercise success and a nonzero exit at every actual child
                # boundary. The synthetic checkout keeps product suites out.
                for failing_stage in (None, 0, 1, 2, 3, 4):
                    with self.subTest(hook=hook, failing_stage=failing_stage):
                        attempts, observations = [], []

                        def probe(
                            args,
                            attempts=attempts,
                            observations=observations,
                            failing_stage=failing_stage,
                            **kwargs,
                        ):
                            stage = len(attempts)
                            attempts.append(args)
                            result = invoke(
                                [
                                    python,
                                    "-c",
                                    "import site, sys; assert not site.ENABLE_USER_SITE; "
                                    "from aethron.example import value; assert value == 1; "
                                    "print('executed', flush=True); sys.exit(int(sys.argv[1]))",
                                    "7" if stage == failing_stage else "0",
                                ],
                                cwd=kwargs["cwd"],
                                env=kwargs["env"],
                                check=kwargs["check"],
                                capture_output=True,
                                text=True,
                                timeout=10,
                            )
                            observations.append(result.stdout)
                            return result

                        with (
                            patch.dict(os.environ, env, clear=True),
                            self.fixture("value = 1") as (output, _),
                            patch.object(verify.subprocess, "run", side_effect=probe),
                        ):
                            if failing_stage is None:
                                verify.run()
                                self.assertIn("PASS:", output.getvalue())
                                self.assertEqual(observations, ["executed\n"] * 5)
                            else:
                                with self.assertRaises(subprocess.CalledProcessError) as caught:
                                    verify.run()
                                self.assertEqual(caught.exception.returncode, 7)
                                self.assertEqual(caught.exception.stdout, "executed\n")
                                self.assertEqual(len(attempts), failing_stage + 1)
                                self.assertEqual(observations, ["executed\n"] * failing_stage)
                                self.assertEqual(output.getvalue(), "")
                            self.assertEqual(dict(os.environ), env)

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
                        "PYTHONNOUSERSITE": value,
                        "AETHRON_TEST_ENV_SENTINEL": "preserved",
                    },
                ),
            ):
                inherited = dict(os.environ)
                with self.fixture("value = 1"), patch.object(verify.subprocess, "run") as child:
                    verify.run()
                self.assertEqual(child.call_count, 5)
                expected = dict(inherited, ORT_DISABLE_TELEMETRY="1", PYTHONNOUSERSITE="1")
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
