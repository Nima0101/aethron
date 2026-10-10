"""Checklist coverage does not approve methods, executions or hardware."""

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from qualification.tests.test_campaign import plan_fixture
from qualification.tests.test_evidence import encoded


def procedure_fixture():
    plan = plan_fixture()
    return {
        "version": 1,
        "kind": "qualification_checklist",
        "rig_sha256": plan["rig_sha256"],
        "domain_sha256": plan["domain_sha256"],
        "cases": [
            {
                "case_id": "blackout",
                "checks": [
                    {"kind": kind, "specification_sha256": str(index) * 64}
                    for index, kind in enumerate(("calibration", "clock", "environment"), 3)
                ],
            }
        ],
    }


def pinned_plan(raw):
    return encoded(dict(plan_fixture(), procedure_sha256=hashlib.sha256(raw).hexdigest()))


class ProcedureTests(unittest.TestCase):
    def validate(self, raw, plan=None):
        self.assertIsNotNone(importlib.util.find_spec("qualification.procedures"))
        from qualification.procedures import validate

        return validate(pinned_plan(raw) if plan is None else plan, raw)

    def test_complete_checklist_remains_unverified(self):
        raw = encoded(procedure_fixture())
        self.assertEqual(
            self.validate(raw),
            {
                "version": 1,
                "plan_sha256": hashlib.sha256(pinned_plan(raw)).hexdigest(),
                "procedure_sha256": hashlib.sha256(raw).hexdigest(),
                "findings": [],
                "procedure_declaration_checks_passed": True,
                "content_status": "consistent_unverified",
                "cases": [
                    {
                        "case_index": 0,
                        "checks": dict.fromkeys(
                            ("calibration", "clock", "environment"), "unverified"
                        ),
                    }
                ],
                "procedure_verified": False,
                "specification_bytes_verified": False,
                "artifact_authenticity_verified": False,
                "physical_qualification_passed": False,
                "human_review_status": "unverified",
            },
        )

    def test_independent_binding_and_coverage_negatives_are_retained(self):
        doc = procedure_fixture()
        doc.update(rig_sha256="a" * 64, domain_sha256="b" * 64)
        doc["cases"][0]["case_id"] = "unplanned"
        doc["cases"][0]["checks"] = [{"kind": "clock", "specification_sha256": None}]
        report = self.validate(encoded(doc), encoded(plan_fixture()))
        self.assertEqual(
            report["findings"],
            [
                "procedure_case_missing",
                "procedure_case_unplanned",
                "procedure_check_missing",
                "procedure_digest_mismatch",
                "procedure_domain_mismatch",
                "procedure_rig_mismatch",
                "procedure_specification_unknown",
            ],
        )
        self.assertFalse(report["procedure_declaration_checks_passed"])
        self.assertEqual(report["content_status"], "incomplete")
        self.assertEqual(set(report["cases"][0]["checks"].values()), {"missing"})

    def test_unknown_and_missing_are_distinct(self):
        doc = procedure_fixture()
        doc["cases"][0]["checks"] = [{"kind": "clock", "specification_sha256": None}]
        report = self.validate(encoded(doc))
        self.assertEqual(
            report["findings"], ["procedure_check_missing", "procedure_specification_unknown"]
        )
        self.assertEqual(
            report["cases"][0]["checks"],
            {"calibration": "missing", "clock": "unknown", "environment": "missing"},
        )
        doc["cases"] = []
        self.assertEqual(
            self.validate(encoded(doc))["findings"],
            ["procedure_case_missing", "procedure_check_missing"],
        )

    def test_raw_bytes_are_pinned_even_when_json_is_equivalent(self):
        raw = encoded(procedure_fixture())
        report = self.validate(raw + b" ", pinned_plan(raw))
        self.assertEqual(report["findings"], ["procedure_digest_mismatch"])
        self.assertEqual(report["procedure_sha256"], hashlib.sha256(raw + b" ").hexdigest())

    def test_schema_rejects_unknown_fields_and_wrong_types_at_each_level(self):
        original = procedure_fixture()
        mutations = [
            ((), "version", True),
            ((), "version", 1.0),
            ((), "version", 2),
            ((), "kind", "execute"),
            ((), "rig_sha256", "A" * 64),
            ((), "domain_sha256", None),
            ((), "cases", {}),
            (("cases", 0), "case_id", "private/path"),
            (("cases", 0), "checks", None),
            (("cases", 0, "checks", 0), "kind", "command"),
            (("cases", 0, "checks", 0), "specification_sha256", False),
            (("cases", 0, "checks", 0), "specification_sha256", "0" * 63),
        ]
        for path in ((), ("cases", 0), ("cases", 0, "checks", 0)):
            for field in ("command", "path", "approved", "physical_qualification_passed"):
                mutations.append((path, field, "PRIVATE"))
        for path, key, value in mutations:
            doc = copy.deepcopy(original)
            target = doc
            for step in path:
                target = target[step]
            target[key] = value
            with self.subTest(path=path, key=key, value=value):
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_procedure$"):
                    self.validate(encoded(doc))

    def test_missing_fields_and_duplicate_identities_are_invalid(self):
        for path in ((), ("cases", 0), ("cases", 0, "checks", 0)):
            doc = procedure_fixture()
            target = doc
            for step in path:
                target = target[step]
            for key in list(target):
                value = target.pop(key)
                with self.subTest(path=path, key=key):
                    with self.assertRaises(ValueError):
                        self.validate(encoded(doc))
                target[key] = value
        for path in (("cases",), ("cases", 0, "checks")):
            doc = procedure_fixture()
            target = doc
            for step in path:
                target = target[step]
            target.append(copy.deepcopy(target[0]))
            with self.assertRaises(ValueError):
                self.validate(encoded(doc))

    def test_untrusted_byte_admission(self):
        raw = encoded(procedure_fixture())
        for bad in (
            raw.replace(b'"version":1', b'"version":1,"version":1'),
            raw.replace(b'"version":1', b'"version":1,"\\u0076ersion":1'),
            raw.replace(b'"kind":"clock"', b'"kind":"clock","kind":"clock"'),
            raw.replace(b'"version":1', b'"version":NaN'),
            raw.replace(b'"version":1', b'"version":1e999'),
            raw.replace(b'"version":1', b'"version":111111111111111111'),
            b'"PRIVATE"',
            b"null",
            b"{}",
            b"\xff",
            b"\xef\xbb\xbf" + raw,
            b"[" * 9 + b"]" * 9,
            raw + b"{}",
            b"PRIVATE",
            bytearray(raw),
            memoryview(raw),
            raw.decode(),
            None,
            raw + b" " * 65536,
        ):
            with self.subTest(kind=type(bad).__name__):
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_procedure$"):
                    self.validate(bad, pinned_plan(raw))

    def test_invalid_plan_is_never_accepted(self):
        raw = encoded(procedure_fixture())
        for bad in (b"{}", b"PRIVATE", bytearray(pinned_plan(raw)), pinned_plan(raw) + b"{}"):
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_procedure$"):
                self.validate(raw, bad)

    def test_exact_bounds_and_plan_order(self):
        doc, plan = procedure_fixture(), plan_fixture()
        doc["cases"] = [
            dict(copy.deepcopy(doc["cases"][0]), case_id=f"case_{i}") for i in range(16)
        ]
        plan["cases"] = [dict(plan["cases"][0], id=f"case_{i}") for i in reversed(range(16))]
        raw = encoded(doc)
        raw += b" " * (65536 - len(raw))
        plan["procedure_sha256"] = hashlib.sha256(raw).hexdigest()
        plan_raw = encoded(plan)
        plan_raw += b" " * (65536 - len(plan_raw))
        report = self.validate(raw, plan_raw)
        self.assertTrue(report["procedure_declaration_checks_passed"])
        self.assertEqual([c["case_index"] for c in report["cases"]], list(range(16)))
        for bad_raw, bad_plan in ((raw + b" ", plan_raw), (raw, plan_raw + b" ")):
            with self.assertRaises(ValueError):
                self.validate(bad_raw, bad_plan)
        doc["cases"].append(dict(doc["cases"][0], case_id="extra"))
        with self.assertRaises(ValueError):
            self.validate(encoded(doc))

    def test_report_omits_case_ids_and_reference_digests(self):
        doc = procedure_fixture()
        doc["cases"][0]["case_id"] = "PRIVATE_ID"
        rendered = json.dumps(self.validate(encoded(doc)))
        self.assertNotIn("PRIVATE", rendered)
        self.assertNotIn("3" * 64, rendered)

    def test_case_and_check_permutation_preserves_states_by_plan_order(self):
        doc, plan = procedure_fixture(), plan_fixture()
        other = copy.deepcopy(doc["cases"][0])
        other["case_id"] = "other"
        other["checks"][0]["specification_sha256"] = None
        doc["cases"].append(other)
        plan["cases"].insert(0, dict(plan["cases"][0], id="other"))
        states = []
        for _ in range(2):
            raw = encoded(doc)
            plan["procedure_sha256"] = hashlib.sha256(raw).hexdigest()
            report = self.validate(raw, encoded(plan))
            self.assertEqual(report["findings"], ["procedure_specification_unknown"])
            states.append(report["cases"])
            doc["cases"].reverse()
            for case in doc["cases"]:
                case["checks"].reverse()
        self.assertEqual(states[0], states[1])
        self.assertEqual(states[0][0]["checks"]["calibration"], "unknown")
        self.assertEqual(states[0][1]["checks"]["calibration"], "unverified")

    def test_token_length_and_type_bounds(self):
        for value in ("", "x" * 65, "é", "\\ud800", None, [], 1, True):
            doc = procedure_fixture()
            doc["cases"][0]["case_id"] = value
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_procedure$"):
                    self.validate(encoded(doc))
        doc, plan = procedure_fixture(), plan_fixture()
        doc["cases"][0]["case_id"] = "a" * 64
        plan["cases"][0]["id"] = "a" * 64
        raw = encoded(doc)
        plan["procedure_sha256"] = hashlib.sha256(raw).hexdigest()
        self.assertTrue(self.validate(raw, encoded(plan))["procedure_declaration_checks_passed"])

    def test_portable_synthetic_vectors(self):
        path = Path(__file__).resolve().parents[1] / "fixtures/procedures-v1.json"
        corpus = json.loads(path.read_text())
        self.assertEqual(corpus["version"], 1)
        self.assertEqual(
            {row["id"] for row in corpus["vectors"]},
            {"complete_unverified", "unknown_clock", "missing_cases", "all_mismatches"},
        )
        for row in corpus["vectors"]:
            with self.subTest(vector=row["id"]):
                self.assertEqual(
                    self.validate(
                        bytes.fromhex(row["procedure_hex"]), bytes.fromhex(row["plan_hex"])
                    ),
                    row["expected_report"],
                )


if __name__ == "__main__":
    unittest.main()
