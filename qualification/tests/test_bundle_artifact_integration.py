"""Real API composition preserves independent evidence limits and failures."""

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from qualification.artifacts import verify
from qualification.campaign_bundle import evaluate
from qualification.tests.test_artifacts import ABC, EMPTY, declaration
from qualification.tests.test_campaign import capture
from qualification.tests.test_campaign_bundle_cli import frame
from qualification.tests.test_campaign_references import reference_plan

ROOT = Path(__file__).resolve().parents[2]


class BundleArtifactIntegrationTests(unittest.TestCase):
    def assert_withheld(self, bundle, artifact):
        for report in (bundle, bundle["coverage"], bundle["references"], artifact):
            self.assertIs(report["physical_qualification_passed"], False)
            self.assertIs(report["artifact_authenticity_verified"], False)
        self.assertIs(bundle["artifact_bytes_verified"], False)
        for report in (bundle, bundle["coverage"], bundle["references"]):
            self.assertIs(report["domain_verified"], False)
            self.assertIs(report["procedure_verified"], False)
        self.assertIs(artifact["declaration"]["physical_qualification_passed"], False)
        self.assertIs(artifact["declaration"]["artifacts_verified"], False)

    def test_freshness_and_supplied_bytes_are_independent_checks(self):
        row = capture(declaration())
        plan = reference_plan()
        input_digest = hashlib.sha256(row["manifest"]).hexdigest()
        commitments = {}
        for fresh, now_ms in ((True, 1050), (False, 1151)):
            current = dict(row, now_ms=now_ms)
            bundle = evaluate(plan, [current], b"abc", b"def")
            commitments[now_ms] = bundle["coverage"]["captures_sha256"]
            for matched in (True, False):
                with self.subTest(fresh=fresh, matched=matched):
                    artifact = verify(
                        current["manifest"],
                        {ABC: b"abc" if matched else b"changed"},
                        now_ms=current["now_ms"],
                    )
                    self.assertIs(bundle["software_checks_passed"], fresh)
                    self.assertIs(artifact["artifact_bytes_verified"], matched)
                    self.assertIs(artifact["software_checks_passed"], fresh and matched)
                    self.assertEqual(artifact["declaration"]["input_sha256"], input_digest)
                    self.assertEqual(
                        artifact["declaration"]["findings"], [] if fresh else ["capture_stale"]
                    )
                    self.assertEqual(
                        artifact["artifact_findings"],
                        [] if matched else ["artifact_digest_mismatch"],
                    )
                    self.assert_withheld(bundle, artifact)
        self.assertNotEqual(commitments[1050], commitments[1151])

    def test_matching_artifacts_do_not_bind_a_substituted_manifest(self):
        original = capture(declaration())
        changed_doc = declaration()
        changed_doc["records"][0]["data"]["valid_until_ms"] = 1049
        changed = capture(changed_doc)
        previous = verify(original["manifest"], {ABC: b"abc"}, now_ms=1050)
        current = verify(changed["manifest"], {ABC: b"abc"}, now_ms=1050)
        bundle = evaluate(reference_plan(), [changed], b"abc", b"def")
        self.assertIs(previous["software_checks_passed"], True)
        self.assertIs(current["artifact_bytes_verified"], True)
        self.assertIs(current["software_checks_passed"], False)
        self.assertIs(bundle["software_checks_passed"], False)
        self.assertNotEqual(
            previous["declaration"]["input_sha256"], current["declaration"]["input_sha256"]
        )
        self.assertEqual(
            current["declaration"]["input_sha256"], hashlib.sha256(changed["manifest"]).hexdigest()
        )
        self.assertEqual(current["declaration"]["findings"], ["calibration_interval"])
        self.assertEqual(
            bundle["coverage"]["findings"],
            ["capture_coverage_missing", "declaration_calibration_interval"],
        )
        self.assert_withheld(bundle, current)

    def test_individually_passing_artifacts_do_not_erase_capture_reuse(self):
        first = capture(declaration())
        second = dict(first, now_ms=1051)
        bundle = evaluate(reference_plan(), [first, second], b"abc", b"def")
        self.assertIs(bundle["software_checks_passed"], False)
        self.assertEqual(
            bundle["coverage"]["findings"], ["capture_coverage_missing", "capture_reused"]
        )
        self.assertEqual(
            bundle["coverage"]["capture_counts"], {"submitted": 2, "eligible": 0, "rejected": 2}
        )
        for row in (first, second):
            artifact = verify(row["manifest"], {ABC: b"abc"}, now_ms=row["now_ms"])
            self.assertIs(artifact["software_checks_passed"], True)
            self.assert_withheld(bundle, artifact)

    def test_stream_and_artifact_api_retain_simultaneous_negatives(self):
        doc = declaration()
        doc["records"][0]["data"]["valid_until_ms"] = 1049
        doc["records"][0]["artifact_sha256"] = "0" * 64
        doc["records"][1]["clock_domain"] = "different-boot"
        row = capture(doc)
        row.update(now_ms=1151, manifest=row["manifest"] + b" \n")
        plan = reference_plan()
        domain, procedure = b"PRIVATE_DOMAIN", b"PRIVATE_PROCEDURE"
        expected = evaluate(plan, [row], domain, procedure)
        result = subprocess.run(
            [sys.executable, "-m", "qualification.campaign_bundle_cli"],
            input=frame(plan, [row], domain, procedure),
            capture_output=True,
            cwd=ROOT,
            timeout=10,
            check=False,
        )
        self.assertEqual((result.returncode, result.stderr), (1, b""))
        bundle = json.loads(result.stdout)
        self.assertEqual(bundle, expected)
        self.assertEqual(
            bundle["coverage"]["findings"],
            [
                "capture_coverage_missing",
                "declaration_calibration_interval",
                "declaration_capture_stale",
                "declaration_clock_domain_mismatch",
            ],
        )
        self.assertEqual(
            bundle["references"]["reference_findings"],
            ["domain_digest_mismatch", "procedure_digest_mismatch"],
        )
        artifact = verify(
            row["manifest"], {ABC: b"PRIVATE_BYTES", EMPTY: b""}, now_ms=row["now_ms"]
        )
        self.assertEqual(
            artifact["declaration"]["input_sha256"], hashlib.sha256(row["manifest"]).hexdigest()
        )
        self.assertEqual(
            artifact["declaration"]["findings"],
            ["calibration_interval", "capture_stale", "clock_domain_mismatch"],
        )
        self.assertEqual(
            artifact["artifact_findings"],
            ["artifact_digest_mismatch", "artifact_missing", "artifact_unreferenced"],
        )
        self.assertIs(artifact["software_checks_passed"], False)
        self.assertIs(bundle["software_checks_passed"], False)
        for private in ("PRIVATE", "synthetic-rig", "different-boot", "thermal"):
            self.assertNotIn(private, json.dumps([bundle, artifact]))
        self.assert_withheld(bundle, artifact)


if __name__ == "__main__":
    unittest.main()
