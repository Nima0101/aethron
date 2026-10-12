"""Review reports must reject source changes observed during their controls."""

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.tests.test_review_results import DRIVERS


class ReviewSourceTests(unittest.TestCase):
    def exercise(self, driver, fault):
        read = Path.read_bytes
        run = driver.run_tests
        state = {"runs": 0}
        target = Path(__file__).parents[2] / "qualification/evidence.py"

        def observed_bytes(path):
            if path == target:
                if fault == "missing_before" or (fault == "missing_after" and state["runs"]):
                    raise OSError("PRIVATE source path unavailable")
                if fault == "changed" and state["runs"]:
                    return read(path) + b"\n# changed during controls\n"
            return read(path)

        def controls(*args, **kwargs):
            result = run(*args, **kwargs)
            state["runs"] += 1
            return result

        output = io.StringIO()
        error = None
        with (
            patch.object(Path, "read_bytes", observed_bytes),
            patch.object(driver, "run_tests", controls),
            contextlib.redirect_stdout(output),
        ):
            try:
                driver.main()
            except (RuntimeError, OSError) as caught:
                error = caught
        return error, output.getvalue(), state["runs"]

    def test_changed_source_cannot_be_reported_as_tested(self):
        for driver, _ in DRIVERS:
            with self.subTest(driver=driver.__name__):
                error, output, runs = self.exercise(driver, "changed")
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), "review_sources_changed")
                self.assertEqual(output, "")
                self.assertGreater(runs, 0)

    def test_unreadable_initial_source_prevents_controls(self):
        for driver, _ in DRIVERS:
            with self.subTest(driver=driver.__name__):
                error, output, runs = self.exercise(driver, "missing_before")
                self.assertEqual(runs, 0)
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), "review_sources_unavailable")
                self.assertEqual(output, "")

    def test_unreadable_final_source_prevents_report(self):
        for driver, _ in DRIVERS:
            with self.subTest(driver=driver.__name__):
                error, output, runs = self.exercise(driver, "missing_after")
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), "review_sources_unavailable")
                self.assertEqual(output, "")
                self.assertGreater(runs, 0)

    def test_stable_sources_retain_real_control_results(self):
        root = Path(__file__).parents[2]
        for driver, count in DRIVERS:
            with self.subTest(driver=driver.__name__):
                error, output, runs = self.exercise(driver, None)
                self.assertIsNone(error)
                report = json.loads(output)
                self.assertEqual(runs, count + 2)
                self.assertEqual(
                    report.get("source_observation"), "equal_before_and_after_controls"
                )
                sources = report["source_sha256"]
                self.assertIn("qualification/technology/source_snapshot.py", sources)
                for name, digest in sources.items():
                    self.assertEqual(digest, hashlib.sha256((root / name).read_bytes()).hexdigest())
                self.assertTrue(report["baseline_passed"])
                self.assertTrue(report["restored_baseline_passed"])
                self.assertIs(report["physical_qualification_passed"], False)
