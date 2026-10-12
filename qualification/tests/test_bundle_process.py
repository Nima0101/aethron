"""Exercise real module startup, binary pipes, exit status and report delivery."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from qualification.tests.test_campaign import capture
from qualification.tests.test_campaign_bundle_cli import frame
from qualification.tests.test_campaign_references import reference_plan

ROOT = Path(__file__).resolve().parents[2]


class BundleProcessTests(unittest.TestCase):
    def invoke(self, raw, args=()):
        result = subprocess.run(
            [sys.executable, "-m", "qualification.campaign_bundle_cli", *args],
            input=raw,
            capture_output=True,
            cwd=ROOT,
            timeout=10,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr

    def test_module_entry_point_reproduces_golden_bytes_twice(self):
        golden = (ROOT / "qualification/evidence/synthetic-campaign-bundle-v1.json").read_bytes()
        for _ in range(2):
            self.assertEqual(self.invoke(frame()), (0, golden, b""))

    def test_negative_exit_preserves_both_failure_groups(self):
        code, out, err = self.invoke(
            frame(reference_plan(), [capture(), capture()], b"bad", b"bad")
        )
        self.assertEqual((code, err), (1, b""))
        report = json.loads(out)
        self.assertIs(report["software_checks_passed"], False)
        self.assertIs(report["physical_qualification_passed"], False)
        self.assertEqual(
            report["coverage"]["findings"], ["capture_coverage_missing", "capture_reused"]
        )
        self.assertEqual(
            report["references"]["reference_findings"],
            ["domain_digest_mismatch", "procedure_digest_mismatch"],
        )
        self.assertEqual(
            out, (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )

    def test_malformed_frame_has_no_stdout_and_fixed_stderr(self):
        self.assertEqual(
            self.invoke(b"PRIVATE broken frame"), (2, b"", b"invalid_campaign_bundle\n")
        )

    def test_unexpected_argument_has_no_stdout_and_fixed_stderr(self):
        self.assertEqual(
            self.invoke(frame(), ["--PRIVATE"]), (2, b"", b"invalid_campaign_bundle\n")
        )


if __name__ == "__main__":
    unittest.main()
