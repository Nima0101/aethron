"""Unsupported filesystem primitives reject without output or filesystem mutation."""

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron.evaluation import splits, synthetic


def script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DatasetPlatform(unittest.TestCase):
    @unittest.skipIf(splits._filesystem_supported(write=True), "native POSIX filesystem available")
    def test_native_unsupported_fixture_cli_has_no_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fixture"
            result = subprocess.run(
                [sys.executable, "-m", "aethron.evaluation.synthetic", str(target)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(
                (result.returncode, result.stdout, result.stderr),
                (2, "", "invalid_fixture_output\n"),
            )
            self.assertFalse(target.exists())

    def test_missing_primitive_rejects_before_creating_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            for missing in ("O_NOFOLLOW", "O_NONBLOCK", "O_DIRECTORY", "dir_fd", "link_follow"):
                target = Path(tmp) / missing
                with self.subTest(missing=missing), patch.dict(os.__dict__):
                    if missing == "dir_fd":
                        os.supports_dir_fd = set()
                    elif missing == "link_follow":
                        os.supports_follow_symlinks = set()
                    else:
                        os.__dict__.pop(missing, None)
                    with self.assertRaisesRegex(ValueError, "^invalid_fixture_output$"):
                        synthetic.generate(target)
                    self.assertFalse(target.exists())

    def test_document_reader_has_fixed_error_without_unsafe_fallback(self):
        with patch.dict(os.__dict__):
            os.__dict__.pop("O_NOFOLLOW", None)
            with self.assertRaisesRegex(ValueError, "^invalid_split_manifest$"):
                splits._read_document("private-path")

    def test_harnesses_reject_before_scratch_creation_or_child_execution(self):
        fuzz = script("dataset_fuzz")
        timing = script("dataset_cli_timing")
        with (
            patch.object(os, "supports_dir_fd", set()),
            patch.object(tempfile, "TemporaryDirectory", side_effect=AssertionError("no scratch")),
            patch.object(timing, "sample", side_effect=AssertionError("no child")),
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_fuzz_input$"):
                fuzz.run(cases=1)
            with self.assertRaisesRegex(ValueError, "^invalid_timing_input$"):
                timing.run("private-path", repetitions=1)

    def test_unsupported_cli_returns_fixed_error_and_no_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fixture"
            fuzz = script("dataset_fuzz")
            for entry, args, error in (
                (synthetic.main, [str(target)], "invalid_fixture_output"),
                (splits.main, ["private-path"], "invalid_split_manifest"),
                (fuzz.main, ["--cases", "1"], "invalid_fuzz_input"),
            ):
                stdout, stderr = io.StringIO(), io.StringIO()
                with (
                    self.subTest(entry=entry),
                    patch.object(os, "supports_dir_fd", set()),
                    patch.object(sys, "argv", ["cli", *args]),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    self.assertEqual(entry(), 2)
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertEqual(stderr.getvalue(), error + "\n")
                self.assertFalse(target.exists())
