"""Negative controls for the fixed installed-package behavioral corpus."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "passport_installed_vectors", ROOT / "scripts/passport_installed_vectors.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class InstalledVectorTests(unittest.TestCase):
    def test_optimized_mode_rejects_before_fixture_reads(self):
        for mode in (1, 2):
            with self.subTest(mode=mode):
                with patch.object(
                    RUNNER, "sys", SimpleNamespace(flags=SimpleNamespace(optimize=mode))
                ):
                    with self.assertRaisesRegex(RuntimeError, "optimized_execution_not_supported"):
                        RUNNER.run(Path("missing-fixture-root"))

    def test_current_corpora_execute_all_checks(self):
        self.assertEqual(RUNNER.run(ROOT), 40)

    def test_missing_or_changed_cases_reject_for_every_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in RUNNER.CORPORA:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                original = (ROOT / relative).read_bytes()
                for mode in ("empty", "truncated", "duplicate", "changed-outcome"):
                    data = json.loads(original)
                    if mode == "empty":
                        data["cases"] = []
                    elif mode == "truncated":
                        data["cases"].pop()
                    elif mode == "duplicate":
                        data["cases"][-1] = data["cases"][0]
                    else:
                        data["cases"][0]["status"] = "unreviewed"
                    path.write_text(json.dumps(data))
                    with self.subTest(path=relative, mode=mode):
                        with self.assertRaisesRegex(ValueError, "invalid_vector_coverage"):
                            RUNNER.load_vectors(root, relative)

    def test_missing_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                RUNNER.load_vectors(Path(directory), next(iter(RUNNER.CORPORA)))

    def test_behavior_mismatch_still_fails_with_intact_corpora(self):
        from aethron.passports import VerificationResult

        with patch.object(
            RUNNER, "verify", return_value=VerificationResult("authenticated", "wrong")
        ):
            with self.assertRaises(AssertionError):
                RUNNER.run(ROOT)


if __name__ == "__main__":
    unittest.main()
