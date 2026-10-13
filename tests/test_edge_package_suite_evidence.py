"""Real synthetic child suites must not qualify skipped or expected-failure coverage."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_package_check as checker


@unittest.skipUnless(importlib.util.find_spec("packaging.utils"), "wheel build dependency")
class PackageSuiteEvidence(unittest.TestCase):
    def probe(self, source):
        execute = subprocess.run
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"

            def copy_fixture(origin, destination):
                Path(destination).write_text(
                    source if Path(origin).name == "test_sensor_packets.py" else ""
                )

            def run(args, **kwargs):
                if "build" in args:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir(exist_ok=True)
                    for name in ("aethron-0.2.0", "aethron_edge-0.1.0"):
                        (destination / (name + "-py3-none-any.whl")).write_bytes(b"fixture")
                elif args[-1] in ("--installed-payload", "--installed-edge-payload"):
                    import hashlib
                    import json

                    selected = "aethron" if args[-1] == "--installed-payload" else "aethron_edge"
                    project = (
                        checker.ROOT
                        if selected == "aethron"
                        else checker.ROOT / "integrations/edge"
                    )
                    manifest = {
                        name: hashlib.sha256(data).hexdigest()
                        for name, data in checker.package_check.snapshot_source_payload(
                            project, selected
                        ).items()
                    }
                    return subprocess.CompletedProcess(args, 0, stdout=json.dumps(manifest))
                elif args[1:] == ["--help"]:
                    return subprocess.CompletedProcess(args, 0, stdout="usage: aethron-edge\n")
                elif "venv" not in args and "pip" not in args:
                    # Exercise the exact production test invocation using this interpreter;
                    # product builds, installs and server launch remain outside this probe.
                    kwargs.update(capture_output=True, text=True, timeout=10)
                    execute([sys.executable, *args[1:]], **kwargs)
                    raise RuntimeError("installed_suite_accepted")
                return subprocess.CompletedProcess(args, 0)

            with (
                patch.object(checker.package_check, "validate_source_payload"),
                patch.object(checker.shutil, "copyfile", side_effect=copy_fixture),
                patch.object(checker.subprocess, "run", side_effect=run),
            ):
                try:
                    checker.run(Path(directory) / "wheelhouse", output)
                except (RuntimeError, subprocess.CalledProcessError) as error:
                    self.assertFalse((output / "result.json").exists())
                    return error
            self.fail("probe unexpectedly completed package qualification")

    def test_incomplete_suites_cannot_qualify(self):
        for source in (
            "",
            "import unittest\n@unittest.skip('synthetic skip')\n"
            "class Case(unittest.TestCase):\n def test_one(self): pass\n",
            "import unittest\nclass Case(unittest.TestCase):\n"
            " @unittest.expectedFailure\n def test_one(self): self.fail('synthetic')\n",
            "import unittest\nclass Case(unittest.TestCase):\n"
            " def test_one(self): pass\n"
            " @unittest.skip('synthetic skip')\n def test_two(self): pass\n",
        ):
            with self.subTest(source=source):
                self.assertIsInstance(self.probe(source), subprocess.CalledProcessError)

    def test_failing_suites_remain_rejected(self):
        for body in ("self.fail('synthetic')", "raise ValueError('synthetic')"):
            with self.subTest(body=body):
                source = f"import unittest\nclass Case(unittest.TestCase):\n def test_one(self): {body}\n"
                self.assertIsInstance(self.probe(source), subprocess.CalledProcessError)

    def test_nonempty_passing_suite_reaches_next_boundary(self):
        error = self.probe(
            "import unittest\nclass Case(unittest.TestCase):\n"
            " def test_one(self): self.assertEqual(2 + 2, 4)\n"
        )
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "installed_suite_accepted")
