"""Synthetic syntax and reporting checks; no fixture or child command executes."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify


class StaticCheckClaims(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, source, failure=None, child_error=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifests = root / "docs/verification"
            manifests.mkdir(parents=True)
            for name in (
                "governance",
                "architecture",
                "amendment-v2",
                "data",
                "amendment-v3",
                "data-v3",
                "registration",
                "rgb-model",
                "rgb-smoke",
            ):
                (manifests / (name + "-freeze.json")).write_text(
                    json.dumps({"files": {}}), encoding="utf-8"
                )
            (root / "aethron").mkdir()
            (root / "aethron/example.py").write_text(source, encoding="utf-8")
            output = io.StringIO()
            calls = []

            def child(args, **kwargs):
                self.assertEqual(kwargs, {"cwd": root, "check": True})
                calls.append(args)
                if len(calls) == failure:
                    if child_error is not None:
                        raise child_error
                    raise subprocess.CalledProcessError(7, args)

            with (
                patch.object(verify, "ROOT", root),
                # Root identity has real-Git coverage in test_verify_root.
                patch.object(verify, "require_worktree_root"),
                patch.object(verify.subprocess, "run", side_effect=child),
                patch.object(verify, "git_output", return_value=b""),
                contextlib.redirect_stdout(output),
            ):
                yield output, calls

    def reject(self, source, error=AssertionError):
        with self.fixture(source) as (output, calls):
            with self.assertRaises(error):
                verify.run()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_selected_import_names_rejected(self):
        for module in ("socket", "requests", "urllib", "pickle", "subprocess", "ctypes"):
            for source in (f"import {module} as alias", f"from {module}.example import value"):
                with self.subTest(source=source):
                    self.reject(source)

    def test_selected_bare_calls_rejected(self):
        for name in ("eval", "exec", "compile"):
            with self.subTest(name=name):
                self.reject(f"{name}('synthetic')")

    def test_unfinished_markers_rejected(self):
        for marker in ("TO" + "DO", "FIX" + "ME"):
            with self.subTest(marker=marker):
                self.reject("# " + marker)

    def test_invalid_syntax_rejected(self):
        self.reject("def (", SyntaxError)

    def test_markers_inside_longer_words_are_not_rejected(self):
        for marker in ("TO" + "DO", "FIX" + "ME"):
            with self.subTest(marker=marker), self.fixture("# prefix" + marker + "suffix"):
                verify.run()

    def test_parse_only_does_not_establish_runtime_or_compilability(self):
        for source in (
            "import math\nvalue = math.sqrt(4)",
            "while True:\n    pass",
            "return 42",
            "raise RuntimeError('fixture must not execute')",
        ):
            with self.subTest(source=source), self.fixture(source) as (_, calls):
                verify.run()
                self.assertEqual(len(calls), 5)

    def test_success_names_checks_without_runtime_bound_claim(self):
        with self.fixture("value = 1") as (output, calls):
            verify.run()
            self.assertEqual(len(calls), 5)
            self.assertEqual(
                output.getvalue(),
                "PASS: freeze hashes, source syntax rules, public-content/links, "
                "tests, dataset, consumer, temporal E2E\n",
            )

    def test_each_child_failure_prevents_success_message(self):
        for failure in range(1, 6):
            with (
                self.subTest(failure=failure),
                self.fixture("value = 1", failure) as (output, calls),
            ):
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    verify.run()
                self.assertEqual(caught.exception.returncode, 7)
                self.assertEqual(len(calls), failure)
                self.assertEqual(output.getvalue(), "")

    def test_child_commands_preserve_interpreter_arguments_and_order(self):
        interpreter = "/synthetic directory/python"
        with (
            self.fixture("value = 1") as (_, calls),
            patch.object(verify.sys, "executable", interpreter),
        ):
            verify.run()
            self.assertEqual(
                calls,
                [
                    [interpreter, "scripts/public_links.py", "HEAD"],
                    [interpreter, "-m", "unittest", "discover", "-s", "tests"],
                    [interpreter, "scripts/evaluate_dataset.py"],
                    [interpreter, "scripts/consumer.py"],
                    [interpreter, "scripts/temporal_e2e.py"],
                ],
            )

    def test_child_launch_error_and_interruption_stop_completion(self):
        for failure in range(1, 6):
            for error in (OSError("synthetic launch failure"), KeyboardInterrupt()):
                with (
                    self.subTest(failure=failure, error=type(error).__name__),
                    self.fixture("value = 1", failure, error) as (output, calls),
                ):
                    with self.assertRaises(type(error)) as caught:
                        verify.run()
                    self.assertIs(caught.exception, error)
                    self.assertEqual(len(calls), failure)
                    self.assertEqual(output.getvalue(), "")
