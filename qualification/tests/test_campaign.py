"""Preregistered metadata coverage never establishes device qualification."""

import hashlib
import importlib.util
import json
import unittest

from qualification.tests.test_evidence import encoded, fixture


def plan_fixture():
    return {
        "version": 1,
        "rig_sha256": hashlib.sha256(encoded(fixture()["rig"])).hexdigest(),
        "domain_sha256": "1" * 64,
        "procedure_sha256": "2" * 64,
        "cases": [
            {
                "id": "blackout",
                "lighting": "zero_visible",
                "required_sensors": ["lwir", "depth"],
                "evidence": "synthetic",
                "minimum_captures": 1,
            }
        ],
    }


def capture(doc=None, case_id="blackout"):
    return {
        "case_id": case_id,
        "manifest": encoded(fixture() if doc is None else doc),
        "now_ms": 1050,
    }


class CampaignTests(unittest.TestCase):
    def evaluate(self, plan, captures):
        self.assertIsNotNone(importlib.util.find_spec("qualification.campaign"))
        from qualification.campaign import evaluate

        return evaluate(plan if type(plan) is bytes else encoded(plan), captures)

    def test_complete_declarations_do_not_qualify_devices_or_domains(self):
        report = self.evaluate(plan_fixture(), [capture()])
        self.assertTrue(report["declaration_coverage_complete"])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["capture_counts"], {"submitted": 1, "eligible": 1, "rejected": 0})
        self.assertEqual(report["cases"], [{"case_index": 0, "required": 1, "eligible": 1}])
        self.assertEqual(report["plan_sha256"], hashlib.sha256(encoded(plan_fixture())).hexdigest())
        for key in (
            "physical_qualification_passed",
            "domain_verified",
            "procedure_verified",
            "artifact_authenticity_verified",
        ):
            self.assertFalse(report[key])

    def test_report_binds_capture_bytes_and_evaluation_instant(self):
        original = self.evaluate(plan_fixture(), [capture()])
        self.assertIn("captures_sha256", original)
        later = dict(capture(), now_ms=1051)
        self.assertNotEqual(
            original["captures_sha256"], self.evaluate(plan_fixture(), [later])["captures_sha256"]
        )
        doc = fixture()
        doc["capture"]["start_ms"] = 1001
        changed = self.evaluate(plan_fixture(), [capture(doc)])
        self.assertNotEqual(original["captures_sha256"], changed["captures_sha256"])
        self.assertTrue(changed["declaration_coverage_complete"])
        self.assertEqual(
            self.evaluate(plan_fixture(), [capture(), capture(doc)]),
            self.evaluate(plan_fixture(), [capture(doc), capture()]),
        )

    def test_missing_case_coverage_and_minimums(self):
        report = self.evaluate(plan_fixture(), [])
        self.assertFalse(report["declaration_coverage_complete"])
        self.assertEqual(report["findings"], ["capture_coverage_missing"])
        plan = plan_fixture()
        plan["cases"][0]["minimum_captures"] = 2
        self.assertEqual(self.evaluate(plan, [capture()])["findings"], ["capture_coverage_missing"])
        doc = fixture()
        doc["capture"]["start_ms"] = 1001
        self.assertTrue(
            self.evaluate(plan, [capture(), capture(doc)])["declaration_coverage_complete"]
        )

    def test_duplicate_capture_invalidates_all_occurrences_in_any_order(self):
        plan = plan_fixture()
        plan["cases"].append(dict(plan["cases"][0], id="recheck"))
        rows = [capture(), capture(case_id="recheck")]
        first = self.evaluate(plan, rows)
        self.assertEqual(first, self.evaluate(plan, list(reversed(rows))))
        self.assertEqual(first["capture_counts"], {"submitted": 2, "eligible": 0, "rejected": 2})
        self.assertEqual(first["findings"], ["capture_coverage_missing", "capture_reused"])

    def test_binding_lighting_sensor_and_evidence_mismatches(self):
        for mutate, finding in (
            (lambda p: p.update(rig_sha256="0" * 64), "capture_rig_mismatch"),
            (lambda p: p["cases"][0].update(lighting="daylight"), "capture_lighting_mismatch"),
            (lambda p: p["cases"][0].update(required_sensors=["radar"]), "capture_sensor_missing"),
            (
                lambda p: p["cases"][0].update(evidence="external_unverified"),
                "capture_evidence_mismatch",
            ),
        ):
            plan = plan_fixture()
            mutate(plan)
            report = self.evaluate(plan, [capture()])
            self.assertFalse(report["declaration_coverage_complete"])
            self.assertIn(finding, report["findings"])

    def test_failed_attempt_retained_alongside_success(self):
        doc = fixture()
        doc["records"][0]["data"]["valid_until_ms"] = 1049
        report = self.evaluate(plan_fixture(), [capture(), capture(doc)])
        self.assertEqual(report["capture_counts"], {"submitted": 2, "eligible": 1, "rejected": 1})
        self.assertEqual(report["findings"], ["declaration_calibration_interval"])
        self.assertFalse(report["declaration_coverage_complete"])

    def test_malformed_and_unplanned_capture_report_fixed_findings(self):
        bad = capture()
        bad["manifest"] = b"PRIVATE_MALFORMED"
        report = self.evaluate(plan_fixture(), [bad, capture(case_id="PRIVATE_CASE")])
        self.assertEqual(
            report["findings"], ["capture_coverage_missing", "capture_invalid", "capture_unplanned"]
        )
        for text in ("PRIVATE", "blackout", "synthetic-rig", "thermal"):
            self.assertNotIn(text, json.dumps(report))

    def test_plan_rejects_nonfinite_duplicate_unknown_and_invalid_fields(self):
        for raw in (
            b"{}",
            b"NaN",
            b"[" * 9 + b"0" + b"]" * 9,
            encoded(plan_fixture()).replace(b'"version":1', b'"version":1,"version":1'),
            encoded(plan_fixture()) + b" " * 65536,
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_capture_campaign$"):
                self.evaluate(raw, [])
        for mutate in (
            lambda p: p.update(physical_qualification_passed=True),
            lambda p: p.update(version=True),
            lambda p: p["cases"][0].update(minimum_captures=True),
            lambda p: p["cases"][0].update(minimum_captures=0),
            lambda p: p["cases"][0].update(minimum_captures=65),
            lambda p: p["cases"][0].update(required_sensors=["depth", "depth"]),
            lambda p: p["cases"].append(p["cases"][0]),
            lambda p: p.update(cases=[dict(p["cases"][0], id=f"c{i}") for i in range(17)]),
            lambda p: p.update(
                cases=[dict(p["cases"][0], id=f"c{i}", minimum_captures=64) for i in range(2)]
            ),
        ):
            plan = plan_fixture()
            mutate(plan)
            with self.assertRaisesRegex(ValueError, "^invalid_capture_campaign$"):
                self.evaluate(plan, [])

    def test_input_types_and_resource_bounds_fail_closed(self):
        for rows in (
            None,
            {},
            [capture()] * 65,
            [dict(capture(), now_ms=True)],
            [dict(capture(), manifest=bytearray(b"{}"))],
            [dict(capture(), manifest=b" " * 65537)],
            [dict(capture(), private_location="PRIVATE")],
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_capture_campaign$"):
                self.evaluate(plan_fixture(), rows)
        report = self.evaluate(plan_fixture(), [capture()] * 64)
        self.assertEqual(report["capture_counts"], {"submitted": 64, "eligible": 0, "rejected": 64})


if __name__ == "__main__":
    unittest.main()
