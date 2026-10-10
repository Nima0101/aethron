"""Domain matrices match joint conditions and never qualify hardware."""

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from qualification.tests.test_campaign import plan_fixture
from qualification.tests.test_evidence import encoded


def domain_fixture():
    plan = plan_fixture()
    case = plan["cases"][0]
    return {
        "version": 1,
        "kind": "qualification_domain",
        "rig_sha256": plan["rig_sha256"],
        "profiles": [{key: case[key] for key in ("lighting", "required_sensors", "evidence")}],
    }


def pinned_plan(raw, plan=None):
    return encoded(
        dict(
            plan_fixture() if plan is None else plan, domain_sha256=hashlib.sha256(raw).hexdigest()
        )
    )


class DomainTests(unittest.TestCase):
    def validate(self, raw, plan=None):
        self.assertIsNotNone(importlib.util.find_spec("qualification.domains"))
        from qualification.domains import validate

        return validate(pinned_plan(raw) if plan is None else plan, raw)

    def test_complete_domain_is_only_a_consistent_declaration(self):
        raw = encoded(domain_fixture())
        self.assertEqual(
            self.validate(raw),
            {
                "version": 1,
                "plan_sha256": hashlib.sha256(pinned_plan(raw)).hexdigest(),
                "domain_sha256": hashlib.sha256(raw).hexdigest(),
                "findings": [],
                "domain_declaration_checks_passed": True,
                "content_status": "consistent_unverified",
                "cases": [{"case_index": 0, "profile_index": 0}],
                "profiles": [{"profile_index": 0, "status": "unverified", "matched_case_count": 1}],
                "domain_verified": False,
                "artifact_authenticity_verified": False,
                "physical_qualification_passed": False,
                "human_review_status": "unverified",
            },
        )

    def test_cartesian_product_does_not_invent_a_supported_combination(self):
        doc = domain_fixture()
        doc["profiles"] = [
            {
                "lighting": "daylight",
                "required_sensors": ["lwir", "depth"],
                "evidence": "synthetic",
            },
            {"lighting": "zero_visible", "required_sensors": ["rgb"], "evidence": "synthetic"},
        ]
        report = self.validate(encoded(doc))
        self.assertEqual(report["findings"], ["domain_case_unmatched", "domain_profile_uncovered"])
        self.assertIsNone(report["cases"][0]["profile_index"])

    def test_sensor_subsets_and_evidence_substitutions_never_match(self):
        for sensors, evidence in (
            (["lwir"], "synthetic"),
            (["lwir", "depth", "radar"], "synthetic"),
            (["lwir", "depth"], "recorded"),
        ):
            doc = domain_fixture()
            doc["profiles"][0].update(required_sensors=sensors, evidence=evidence)
            report = self.validate(encoded(doc))
            self.assertEqual(
                report["findings"], ["domain_case_unmatched", "domain_profile_uncovered"]
            )

    def test_null_fields_are_unknown_not_wildcards(self):
        for key in ("lighting", "required_sensors", "evidence"):
            doc = domain_fixture()
            doc["profiles"][0][key] = None
            report = self.validate(encoded(doc))
            self.assertEqual(
                report["findings"], ["domain_case_unmatched", "domain_profile_unknown"]
            )
            self.assertEqual(
                report["profiles"],
                [{"profile_index": 0, "status": "unknown", "matched_case_count": 0}],
            )

    def test_all_independent_negative_findings_are_retained(self):
        doc = domain_fixture()
        doc["rig_sha256"] = "a" * 64
        doc["profiles"][0]["lighting"] = "daylight"
        doc["profiles"].append({"lighting": None, "required_sensors": None, "evidence": None})
        report = self.validate(encoded(doc), encoded(plan_fixture()))
        self.assertEqual(
            report["findings"],
            [
                "domain_case_unmatched",
                "domain_digest_mismatch",
                "domain_profile_uncovered",
                "domain_profile_unknown",
                "domain_rig_mismatch",
            ],
        )
        self.assertFalse(report["domain_declaration_checks_passed"])
        self.assertEqual(report["content_status"], "incomplete")

    def test_empty_profiles_never_pass(self):
        doc = dict(domain_fixture(), profiles=[])
        self.assertEqual(
            self.validate(encoded(doc))["findings"],
            ["domain_case_unmatched", "domain_profiles_missing"],
        )

    def test_semantically_equal_bytes_must_still_match_the_pin(self):
        raw = encoded(domain_fixture())
        self.assertEqual(
            self.validate(raw + b" ", pinned_plan(raw))["findings"], ["domain_digest_mismatch"]
        )

    def test_duplicate_profiles_include_sensor_permutations_and_nulls(self):
        for unknown in (False, True):
            doc = domain_fixture()
            if unknown:
                doc["profiles"][0]["lighting"] = None
            other = copy.deepcopy(doc["profiles"][0])
            other["required_sensors"].reverse()
            doc["profiles"].append(other)
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_domain$"):
                self.validate(encoded(doc))

    def test_profile_order_and_sensor_order_only_change_ordinal_links(self):
        doc, plan = domain_fixture(), plan_fixture()
        doc["profiles"].append(dict(doc["profiles"][0], lighting="daylight"))
        plan["cases"].append(dict(plan["cases"][0], id="second", lighting="daylight"))
        plan["cases"].append(dict(plan["cases"][0], id="repeat"))
        doc["profiles"].reverse()
        doc["profiles"][1]["required_sensors"].reverse()
        raw = encoded(doc)
        report = self.validate(raw, pinned_plan(raw, plan))
        self.assertTrue(report["domain_declaration_checks_passed"])
        self.assertEqual([row["profile_index"] for row in report["cases"]], [1, 0, 1])
        self.assertEqual([row["matched_case_count"] for row in report["profiles"]], [1, 2])

    def test_closed_schema_rejects_wrong_types_and_authority_fields(self):
        mutations = [
            ((), "version", True),
            ((), "version", 1.0),
            ((), "version", 2),
            ((), "kind", "execute"),
            ((), "rig_sha256", "A" * 64),
            ((), "profiles", None),
        ]
        for key, value in (
            ("lighting", []),
            ("lighting", "night"),
            ("evidence", "live_verified"),
            ("required_sensors", []),
            ("required_sensors", ["lwir", "lwir"]),
            ("required_sensors", [True]),
            ("required_sensors", "rgb"),
        ):
            mutations.append((("profiles", 0), key, value))
        for path in ((), ("profiles", 0)):
            for key in ("command", "approved", "domain_verified", "path"):
                mutations.append((path, key, "PRIVATE"))
        for path, key, value in mutations:
            doc = domain_fixture()
            target = doc
            for step in path:
                target = target[step]
            target[key] = value
            with self.subTest(path=path, key=key):
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_domain$"):
                    self.validate(encoded(doc))

    def test_byte_admission_and_missing_keys(self):
        raw = encoded(domain_fixture())
        for bad in (
            None,
            raw.decode(),
            bytearray(raw),
            memoryview(raw),
            b"{}",
            b"null",
            b"PRIVATE",
            b"\xff",
            b"\xef\xbb\xbf" + raw,
            raw + b"{}",
            b"[" * 9 + b"]" * 9,
            raw.replace(b'"version":1', b'"version":1,"version":1'),
            raw.replace(b'"version":1', b'"version":1,"\\u0076ersion":1'),
            raw.replace(b'"version":1', b'"version":NaN'),
            raw.replace(b'"version":1', b'"version":1e999'),
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_domain$"):
                self.validate(bad, pinned_plan(raw))
        for path in ((), ("profiles", 0)):
            doc = domain_fixture()
            target = doc
            for step in path:
                target = target[step]
            for key in list(target):
                old = target.pop(key)
                with self.assertRaises(ValueError):
                    self.validate(encoded(doc))
                target[key] = old
        for plan in (b"{}", b"PRIVATE", bytearray(pinned_plan(raw))):
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_domain$"):
                self.validate(raw, plan)

    def test_exact_byte_and_profile_limits(self):
        doc, plan = domain_fixture(), plan_fixture()
        profiles = []
        for lighting in ("daylight", "low_light", "near_dark", "zero_visible"):
            for sensor in ("rgb", "lwir", "radar", "depth"):
                profiles.append(
                    {"lighting": lighting, "required_sensors": [sensor], "evidence": "synthetic"}
                )
        doc["profiles"] = profiles
        plan["cases"] = [
            dict(row, id=f"case_{i}", minimum_captures=1) for i, row in enumerate(profiles)
        ]
        raw = encoded(doc)
        raw += b" " * (65536 - len(raw))
        plan_raw = pinned_plan(raw, plan)
        plan_raw += b" " * (65536 - len(plan_raw))
        self.assertTrue(self.validate(raw, plan_raw)["domain_declaration_checks_passed"])
        for a, b in ((raw + b" ", plan_raw), (raw, plan_raw + b" ")):
            with self.assertRaises(ValueError):
                self.validate(a, b)
        doc["profiles"].append(dict(profiles[0], required_sensors=["nir"]))
        with self.assertRaises(ValueError):
            self.validate(encoded(doc))

    def test_reports_omit_case_ids(self):
        raw, plan = encoded(domain_fixture()), plan_fixture()
        plan["cases"][0]["id"] = "PRIVATE_ID"
        self.assertNotIn("PRIVATE", json.dumps(self.validate(raw, pinned_plan(raw, plan))))

    def test_existing_checklist_and_bundle_remain_separate_non_qualifying_gates(self):
        from qualification.campaign_bundle import evaluate
        from qualification.procedures import validate as checklist
        from qualification.tests.test_campaign import capture
        from qualification.tests.test_procedures import procedure_fixture

        domain = encoded(domain_fixture())
        plan = json.loads(pinned_plan(domain))
        procedure = procedure_fixture()
        procedure["domain_sha256"] = plan["domain_sha256"]
        procedure_raw = encoded(procedure)
        plan["procedure_sha256"] = hashlib.sha256(procedure_raw).hexdigest()
        plan_raw = encoded(plan)
        reports = [
            self.validate(domain, plan_raw),
            checklist(plan_raw, procedure_raw),
            evaluate(plan_raw, [capture()], domain, procedure_raw),
        ]
        for report, flag in zip(
            reports,
            (
                "domain_declaration_checks_passed",
                "procedure_declaration_checks_passed",
                "software_checks_passed",
            ),
        ):
            self.assertTrue(report[flag])
            self.assertFalse(report["physical_qualification_passed"])
        self.assertFalse(reports[0]["domain_verified"])
        self.assertFalse(reports[1]["procedure_verified"])
        self.assertFalse(reports[2]["domain_verified"])

    def test_portable_vectors(self):
        path = Path(__file__).resolve().parents[1] / "fixtures/domains-v1.json"
        corpus = json.loads(path.read_text())
        self.assertEqual(corpus["version"], 1)
        self.assertEqual(
            {row["id"] for row in corpus["vectors"]},
            {"consistent_unverified", "unknown_lighting", "empty_domain", "joint_mismatch"},
        )
        for row in corpus["vectors"]:
            with self.subTest(vector=row["id"]):
                self.assertEqual(
                    self.validate(bytes.fromhex(row["domain_hex"]), bytes.fromhex(row["plan_hex"])),
                    row["expected_report"],
                )


if __name__ == "__main__":
    unittest.main()
