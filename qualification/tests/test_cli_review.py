"""The report CLI must admit one unambiguous evaluation instant."""

import subprocess
import sys
import unittest
from pathlib import Path


class CliReviewTests(unittest.TestCase):
    def invoke(self, args, rig="synthetic-v1.json"):
        root = Path(__file__).resolve().parents[2]
        return subprocess.run(
            [sys.executable, "-m", "qualification", *args],
            input=(root / "qualification/rigs" / rig).read_bytes(),
            capture_output=True,
            timeout=10,
            cwd=root,
            check=False,
        )

    def reject(self, args):
        result = self.invoke(args)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"invalid_qualification_manifest\n")

    def test_repeated_time_cannot_override_stale_evaluation(self):
        for args in (
            ["--now-ms", "1151", "--now-ms", "1050"],
            ["--now-ms=1050", "--now-ms=1151"],
            ["--now-ms", "1050", "--now-ms=1050"],
        ):
            with self.subTest(args=args):
                self.reject(args)

    def test_abbreviated_time_option_is_rejected(self):
        for option in ("--now", "--now-m", "--n"):
            with self.subTest(option=option):
                self.reject([option, "1050"])

    def test_single_time_forms_preserve_exact_golden_reports(self):
        root = Path(__file__).resolve().parents[1]
        for rig, report, status in (
            ("synthetic-v1.json", "synthetic-report-v1.json", 0),
            ("expired-calibration-v1.json", "expired-calibration-report-v1.json", 1),
        ):
            for args in (["--now-ms", "1050"], ["--now-ms=1050"]):
                with self.subTest(rig=rig, args=args):
                    result = self.invoke(args, rig)
                    self.assertEqual(result.returncode, status)
                    self.assertEqual(result.stdout, (root / "evidence" / report).read_bytes())
                    self.assertEqual(result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
