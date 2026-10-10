"""Method contents stay declarations, including when byte binding succeeds."""

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from qualification.tests.test_evidence import encoded
from qualification.tests.test_procedures import pinned_plan, procedure_fixture


def method_doc(kind):
    rules = {"rig_binding": "exact", "clock_domain": "capture"}
    if kind == "calibration":
        rules["interval"] = "entire_capture"
    else:
        rules.update(within_capture="required", max_age_ms=100)
        if kind == "clock":
            rules.update(reference_skew_ms=50, pair_skew_ms=50)
        else:
            rules["lighting"] = "campaign_case"
    return {"version": 1, "kind": "qualification_declaration_method", "check": kind, "rules": rules}


def inputs(docs=None):
    procedure, methods = procedure_fixture(), {}
    docs = docs or {kind: method_doc(kind) for kind in ("calibration", "clock", "environment")}
    for entry in procedure["cases"][0]["checks"]:
        raw = encoded(docs[entry["kind"]])
        digest = hashlib.sha256(raw).hexdigest()
        entry["specification_sha256"] = digest
        methods[digest] = raw
    raw = encoded(procedure)
    return pinned_plan(raw), raw, methods


class MethodTests(unittest.TestCase):
    def verify(self, *args):
        self.assertIsNotNone(importlib.util.find_spec("qualification.methods"))
        from qualification.methods import verify

        return verify(*args)

    def test_bound_content_remains_unverified(self):
        plan, procedure, methods = inputs()
        report = self.verify(plan, procedure, methods)
        self.assertTrue(report["method_bytes_verified"])
        self.assertTrue(report["software_checks_passed"])
        self.assertEqual(report["method_findings"], [])
        self.assertEqual(
            report["method_counts"],
            {"referenced": 3, "supplied": 3, "supplied_bytes": sum(map(len, methods.values()))},
        )
        for key in (
            "method_verified",
            "artifact_authenticity_verified",
            "physical_qualification_passed",
        ):
            self.assertIs(report[key], False)
        self.assertEqual(report["human_review_status"], "unverified")
        pairs = sorted([key, hashlib.sha256(value).hexdigest()] for key, value in methods.items())
        expected = hashlib.sha256(
            b"aethron.qualification.methods.v1\0"
            + json.dumps(pairs, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()
        self.assertEqual(report["methods_sha256"], expected)

    def test_missing_mismatched_unreferenced_and_invalid_are_all_retained(self):
        plan, procedure, methods = inputs()
        keys = list(methods)
        del methods[keys[0]]
        methods[keys[1]] = b"PRIVATE_BAD_CONTENT"
        raw = encoded(method_doc("clock")) + b" "
        methods[hashlib.sha256(raw).hexdigest()] = raw
        report = self.verify(plan, procedure, methods)
        self.assertEqual(
            report["method_findings"],
            ["method_digest_mismatch", "method_invalid", "method_missing", "method_unreferenced"],
        )
        self.assertFalse(report["method_bytes_verified"])
        self.assertFalse(report["software_checks_passed"])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_unknown_and_changed_rules_do_not_change_frozen_execution(self):
        docs = {kind: method_doc(kind) for kind in ("calibration", "clock", "environment")}
        docs["clock"]["rules"].update(reference_skew_ms=51, pair_skew_ms=None)
        report = self.verify(*inputs(docs))
        self.assertTrue(report["method_bytes_verified"])
        self.assertFalse(report["software_checks_passed"])
        self.assertEqual(report["method_findings"], ["method_rule_mismatch", "method_rule_unknown"])
        for value in (0, 49, 51, 2**53 - 1000):
            docs["clock"]["rules"].update(reference_skew_ms=value, pair_skew_ms=50)
            self.assertEqual(
                self.verify(*inputs(docs))["method_findings"], ["method_rule_mismatch"]
            )

    def test_reusing_one_method_for_another_check_is_rejected(self):
        docs = {kind: method_doc("clock") for kind in ("calibration", "clock", "environment")}
        report = self.verify(*inputs(docs))
        self.assertTrue(report["method_bytes_verified"])
        self.assertEqual(report["method_findings"], ["method_check_mismatch"])

    def test_content_admission_preserves_other_evidence(self):
        valid = encoded(method_doc("clock"))
        invalid = [
            b"{}",
            b"null",
            b"\xff",
            b"[" * 9 + b"]" * 9,
            valid.replace(b'"version":1', b'"version":1,"version":1'),
            valid.replace(b'"version":1', b'"version":true'),
            valid.replace(b'"max_age_ms":100', b'"max_age_ms":100.0'),
            valid.replace(b'"max_age_ms":100', b'"max_age_ms":NaN'),
            valid.replace(b'"max_age_ms":100', b'"max_age_ms":-1'),
            encoded(dict(method_doc("clock"), command="PRIVATE")),
        ]
        for bad in invalid:
            plan, procedure, methods = inputs()
            doc = json.loads(procedure)
            entry = doc["cases"][0]["checks"][1]
            del methods[entry["specification_sha256"]]
            digest = hashlib.sha256(bad).hexdigest()
            entry["specification_sha256"] = digest
            methods[digest] = bad
            procedure = encoded(doc)
            report = self.verify(pinned_plan(procedure), procedure, methods)
            self.assertTrue(report["method_bytes_verified"])
            self.assertEqual(report["method_findings"], ["method_invalid"])
            self.assertFalse(report["software_checks_passed"])

    def test_checklist_failure_cannot_be_overridden_by_valid_methods(self):
        plan, procedure, methods = inputs()
        doc = json.loads(procedure)
        doc["rig_sha256"] = "a" * 64
        procedure = encoded(doc)
        report = self.verify(pinned_plan(procedure), procedure, methods)
        self.assertEqual(report["method_findings"], [])
        self.assertFalse(report["software_checks_passed"])
        self.assertIn("procedure_rig_mismatch", report["procedure"]["findings"])

    def test_unknown_or_absent_references_never_pass(self):
        for cases in (
            [],
            [{"case_id": "blackout", "checks": [{"kind": "clock", "specification_sha256": None}]}],
        ):
            doc = dict(procedure_fixture(), cases=cases)
            raw = encoded(doc)
            report = self.verify(pinned_plan(raw), raw, {})
            self.assertEqual(report["method_findings"], ["method_references_empty"])
            self.assertFalse(report["software_checks_passed"])
            self.assertFalse(report["method_bytes_verified"])

    def test_commitment_includes_rejected_payloads_and_is_order_independent(self):
        plan, procedure, methods = inputs()
        baseline = self.verify(plan, procedure, methods)["methods_sha256"]
        self.assertEqual(
            baseline,
            self.verify(plan, procedure, dict(reversed(list(methods.items()))))["methods_sha256"],
        )
        methods["f" * 64] = b"rejected"
        changed = self.verify(plan, procedure, methods)["methods_sha256"]
        self.assertNotEqual(baseline, changed)
        methods["f" * 64] += b" "
        self.assertNotEqual(changed, self.verify(plan, procedure, methods)["methods_sha256"])

    def test_envelope_types_and_limits(self):
        plan, procedure, methods = inputs()
        for bad in (
            None,
            [],
            {"BAD": b"x"},
            {"a" * 64: bytearray(b"x")},
            {"a" * 64: b"x" * 65537},
            {f"{i:064x}": b"" for i in range(49)},
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_methods$"):
                self.verify(plan, procedure, bad)
        payload = b" " * 65536
        full = {f"{i:064x}": payload for i in range(48)}
        report = self.verify(plan, procedure, full)
        self.assertEqual(report["method_counts"]["supplied_bytes"], 3145728)
        self.assertFalse(report["software_checks_passed"])
        for a, b in ((b"PRIVATE", procedure), (plan, bytearray(procedure))):
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_methods$"):
                self.verify(a, b, methods)

    def test_method_rule_keys_types_and_text_are_closed(self):
        original = method_doc("calibration")
        variants = []
        for key in original["rules"]:
            doc = copy.deepcopy(original)
            del doc["rules"][key]
            variants.append(doc)
        for value in (True, [], "bad/path", "x" * 65):
            doc = copy.deepcopy(original)
            doc["rules"]["interval"] = value
            variants.append(doc)
        for doc in variants:
            docs = {kind: method_doc(kind) for kind in ("calibration", "clock", "environment")}
            docs["calibration"] = doc
            self.assertEqual(self.verify(*inputs(docs))["method_findings"], ["method_invalid"])

    def test_partial_unknown_checklist_cannot_pass_with_remaining_bound_methods(self):
        plan, raw, methods = inputs()
        doc = json.loads(raw)
        entry = doc["cases"][0]["checks"][0]
        del methods[entry["specification_sha256"]]
        entry["specification_sha256"] = None
        raw = encoded(doc)
        report = self.verify(pinned_plan(raw), raw, methods)
        self.assertTrue(report["method_bytes_verified"])
        self.assertEqual(report["method_findings"], [])
        self.assertFalse(report["software_checks_passed"])
        self.assertIn("procedure_specification_unknown", report["procedure"]["findings"])

    def test_exact_size_valid_methods_and_repeated_uses(self):
        _, raw, methods = inputs()
        doc = json.loads(raw)
        padded = {}
        for entry in doc["cases"][0]["checks"]:
            payload = methods[entry["specification_sha256"]]
            payload += b" " * (65536 - len(payload))
            digest = hashlib.sha256(payload).hexdigest()
            entry["specification_sha256"] = digest
            padded[digest] = payload
        other = copy.deepcopy(doc["cases"][0])
        other["case_id"] = "repeat"
        doc["cases"].append(other)
        raw = encoded(doc)
        plan = json.loads(pinned_plan(raw))
        plan["cases"].append(dict(plan["cases"][0], id="repeat"))
        report = self.verify(encoded(plan), raw, padded)
        self.assertTrue(report["software_checks_passed"])
        self.assertEqual(
            report["method_counts"], {"referenced": 3, "supplied": 3, "supplied_bytes": 196608}
        )

    def test_portable_vectors(self):
        corpus = json.loads(
            (Path(__file__).resolve().parents[1] / "fixtures/methods-v1.json").read_text()
        )
        self.assertEqual(
            {row["id"] for row in corpus["vectors"]},
            {"consistent_unverified", "unknown_and_mismatch", "missing_and_corrupt"},
        )
        for row in corpus["vectors"]:
            with self.subTest(vector=row["id"]):
                self.assertEqual(
                    self.verify(
                        bytes.fromhex(row["plan_hex"]),
                        bytes.fromhex(row["procedure_hex"]),
                        {key: bytes.fromhex(value) for key, value in row["methods_hex"].items()},
                    ),
                    row["expected_report"],
                )


if __name__ == "__main__":
    unittest.main()
