"""All qualification software gates must hold for the same raw submission."""

import hashlib
import importlib.util
import itertools
import json
import unittest
from unittest.mock import patch

from qualification.tests.test_artifacts import ABC, declaration
from qualification.tests.test_campaign import capture
from qualification.tests.test_domains import domain_fixture
from qualification.tests.test_evidence import encoded
from qualification.tests.test_methods import inputs as method_inputs


def inputs():
    plan, procedure, methods = method_inputs()
    plan, procedure = json.loads(plan), json.loads(procedure)
    domain = encoded(domain_fixture())
    plan["domain_sha256"] = hashlib.sha256(domain).hexdigest()
    procedure["domain_sha256"] = plan["domain_sha256"]
    procedure = encoded(procedure)
    plan["procedure_sha256"] = hashlib.sha256(procedure).hexdigest()
    rows = [dict(capture(declaration()), artifacts={ABC: b"abc"})]
    return encoded(plan), rows, domain, procedure, methods


class AssessmentTests(unittest.TestCase):
    def evaluate(self, *args):
        self.assertIsNotNone(importlib.util.find_spec("qualification.assessment"))
        from qualification.assessment import evaluate

        return evaluate(*args)

    def test_all_software_gates_pass_without_qualification(self):
        report = self.evaluate(*inputs())
        self.assertIs(report["software_checks_passed"], True)
        self.assertIs(report["artifact_bytes_verified"], True)
        self.assertIs(report["coverage"]["declaration_coverage_complete"], True)
        self.assertIs(report["domain"]["domain_declaration_checks_passed"], True)
        self.assertIs(report["methods"]["software_checks_passed"], True)
        self.assertEqual(report["captures"][0]["findings"], [])
        self.assertIs(report["captures"][0]["report"]["software_checks_passed"], True)
        for name in (
            "domain_verified",
            "procedure_verified",
            "method_verified",
            "artifact_authenticity_verified",
            "physical_qualification_passed",
        ):
            self.assertIs(report[name], False)
        self.assertEqual(report["human_review_status"], "unverified")

    def test_every_independent_gate_is_required(self):
        for fresh, domain_ok, method_ok, artifact_ok in itertools.product((False, True), repeat=4):
            plan, rows, domain, procedure, methods = inputs()
            if not fresh:
                rows[0]["now_ms"] = 1151
            if not domain_ok:
                doc = json.loads(domain)
                doc["profiles"][0]["lighting"] = None
                domain = encoded(doc)
            if not method_ok:
                methods.pop(next(iter(methods)))
            if not artifact_ok:
                rows[0]["artifacts"][ABC] = b"wrong"
            with self.subTest(gates=(fresh, domain_ok, method_ok, artifact_ok)):
                report = self.evaluate(plan, rows, domain, procedure, methods)
                self.assertIs(
                    report["software_checks_passed"],
                    all((fresh, domain_ok, method_ok, artifact_ok)),
                )
                self.assertIs(report["coverage"]["declaration_coverage_complete"], fresh)
                self.assertIs(report["domain"]["domain_declaration_checks_passed"], domain_ok)
                self.assertIs(report["methods"]["software_checks_passed"], method_ok)
                self.assertIs(report["artifact_bytes_verified"], artifact_ok)
                self.assertIs(
                    report["captures"][0]["report"]["software_checks_passed"], fresh and artifact_ok
                )

    def test_duplicate_capture_failure_survives_individually_passing_artifacts(self):
        plan, rows, domain, procedure, methods = inputs()
        rows.append(dict(rows[0], now_ms=1051))
        report = self.evaluate(plan, rows, domain, procedure, methods)
        self.assertFalse(report["software_checks_passed"])
        self.assertTrue(report["artifact_bytes_verified"])
        self.assertIn("capture_reused", report["coverage"]["findings"])
        self.assertTrue(all(row["report"]["software_checks_passed"] for row in report["captures"]))

    def test_malformed_capture_does_not_erase_other_negative_evidence(self):
        plan, rows, domain, procedure, methods = inputs()
        rows.append(dict(rows[0], manifest=b"PRIVATE", case_id="PRIVATE_CASE"))
        rows[0]["artifacts"][ABC] = b"PRIVATE_ARTIFACT"
        methods[next(iter(methods))] = b"PRIVATE_METHOD"
        report = self.evaluate(plan, rows, domain + b" ", procedure, methods)
        self.assertEqual(
            report["captures"][1],
            {"capture_index": 1, "findings": ["capture_invalid"], "report": None},
        )
        self.assertIn(
            "artifact_digest_mismatch", report["captures"][0]["report"]["artifact_findings"]
        )
        self.assertIn("domain_digest_mismatch", report["domain"]["findings"])
        self.assertIn("capture_unplanned", report["coverage"]["findings"])
        self.assertIn("method_invalid", report["methods"]["method_findings"])
        self.assertFalse(report["artifact_bytes_verified"])
        self.assertFalse(report["software_checks_passed"])
        for text in ("PRIVATE", "blackout", "synthetic-rig"):
            self.assertNotIn(text, json.dumps(report))

    def test_empty_capture_set_is_not_vacuous_success(self):
        plan, _, domain, procedure, methods = inputs()
        report = self.evaluate(plan, [], domain, procedure, methods)
        self.assertFalse(report["artifact_bytes_verified"])
        self.assertFalse(report["software_checks_passed"])
        self.assertEqual(report["captures"], [])

    def test_checklist_failure_still_blocks_otherwise_valid_submission(self):
        plan, rows, domain, procedure, methods = inputs()
        doc = json.loads(procedure)
        doc["rig_sha256"] = "f" * 64
        procedure = encoded(doc)
        doc = json.loads(plan)
        doc["procedure_sha256"] = hashlib.sha256(procedure).hexdigest()
        report = self.evaluate(encoded(doc), rows, domain, procedure, methods)
        self.assertEqual(report["methods"]["method_findings"], [])
        self.assertIn("procedure_rig_mismatch", report["methods"]["procedure"]["findings"])
        self.assertFalse(report["software_checks_passed"])

    def test_submission_commitment_is_reproducible_and_covers_rejected_bytes(self):
        plan, rows, domain, procedure, methods = inputs()
        rows.append(dict(rows[0], now_ms=1051, artifacts={"0" * 64: b"bad"}))
        methods["f" * 64] = b"bad-method"
        report = self.evaluate(plan, rows, domain, procedure, methods)

        def sha(raw):
            return hashlib.sha256(raw).hexdigest()

        method_digest = sha(
            b"aethron.qualification.methods.v1\0"
            + encoded(sorted([key, sha(raw)] for key, raw in methods.items()))
        )
        bindings = sorted(
            [
                row["case_id"],
                sha(row["manifest"]),
                row["now_ms"],
                sorted([key, sha(raw)] for key, raw in row["artifacts"].items()),
            ]
            for row in rows
        )
        expected = sha(
            b"aethron.qualification.assessment.v1\0"
            + encoded([sha(plan), sha(domain), sha(procedure), method_digest, bindings])
        )
        self.assertEqual(report["submission_sha256"], expected)
        reordered = self.evaluate(
            plan, list(reversed(rows)), domain, procedure, dict(reversed(list(methods.items())))
        )
        self.assertEqual(reordered["submission_sha256"], expected)
        for field in (
            "instant",
            "manifest",
            "artifact",
            "method",
            "plan",
            "domain",
            "procedure",
            "case",
            "duplicate",
        ):
            p, rs, d, proc, ms = inputs()
            original = self.evaluate(p, rs, d, proc, ms)["submission_sha256"]
            if field == "instant":
                rs[0]["now_ms"] += 1
            elif field == "manifest":
                rs[0]["manifest"] += b" "
            elif field == "artifact":
                rs[0]["artifacts"]["0" * 64] = b"rejected"
            elif field == "method":
                ms["0" * 64] = b"rejected"
            elif field == "plan":
                p += b" "
            elif field == "domain":
                d += b" "
            elif field == "procedure":
                proc += b" "
            elif field == "case":
                rs[0]["case_id"] = "unplanned"
            else:
                rs.append(dict(rs[0]))
            with self.subTest(field=field):
                self.assertNotEqual(
                    original, self.evaluate(p, rs, d, proc, ms)["submission_sha256"]
                )

    def test_snapshot_survives_caller_changes_after_admission(self):
        from qualification.assessment import evaluate_coverage

        args = inputs()
        expected = self.evaluate(*args)

        def change_caller(plan, rows):
            args[1][0]["manifest"] = b"PRIVATE"
            args[1][0]["artifacts"].clear()
            args[1].clear()
            args[4].clear()
            return evaluate_coverage(plan, rows)

        with patch("qualification.assessment.evaluate_coverage", side_effect=change_caller):
            self.assertEqual(self.evaluate(*args), expected)

    def test_invalid_envelopes_never_become_reports(self):
        for bad in (
            None,
            (),
            {"software_checks_passed": True},
            [dict(inputs()[1][0], approval=True)],
            inputs()[1] * 65,
        ):
            plan, _, domain, procedure, methods = inputs()
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_assessment$"):
                self.evaluate(plan, bad, domain, procedure, methods)
        for field, value in (
            ("now_ms", True),
            ("case_id", "PRIVATE/PATH"),
            ("manifest", bytearray(b"{}")),
            ("manifest", b"x" * 65537),
            ("artifacts", []),
            ("artifacts", {"BAD": b""}),
            ("artifacts", {ABC: bytearray(b"abc")}),
            ("artifacts", {ABC: b"x" * 1048577}),
            ("artifacts", {f"{i:064x}": b"" for i in range(16)}),
        ):
            args = inputs()
            args[1][0][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_assessment$"):
                    self.evaluate(*args)
        for index in (0, 2, 3, 4):
            args = list(inputs())
            args[index] = {"software_checks_passed": True}
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_assessment$"):
                self.evaluate(*args)

    def test_aggregate_artifact_limit_counts_reused_payloads(self):
        plan, rows, domain, procedure, methods = inputs()
        payload = b"x" * 1048576
        row = dict(rows[0], artifacts={hashlib.sha256(payload).hexdigest(): payload})
        report = self.evaluate(plan, [row] * 4, domain, procedure, methods)
        self.assertEqual(
            sum(r["report"]["artifact_counts"]["supplied_bytes"] for r in report["captures"]),
            4194304,
        )
        self.assertFalse(report["software_checks_passed"])
        with self.assertRaisesRegex(ValueError, "^invalid_qualification_assessment$"):
            self.evaluate(plan, [row] * 5, domain, procedure, methods)
        with self.assertRaisesRegex(ValueError, "^invalid_qualification_assessment$"):
            self.evaluate(
                plan, [row] * 4 + [dict(row, artifacts={ABC: b"x"})], domain, procedure, methods
            )
        full = [dict(rows[0], artifacts={f"{i:064x}": b"" for i in range(15)})] * 64
        self.assertEqual(len(self.evaluate(plan, full, domain, procedure, methods)["captures"]), 64)

    def test_nested_reports_equal_existing_gate_outputs(self):
        from qualification.artifacts import verify
        from qualification.campaign import evaluate
        from qualification.domains import validate
        from qualification.methods import verify as methods_verify

        plan, rows, domain, procedure, methods = inputs()
        report = self.evaluate(plan, rows, domain, procedure, methods)
        capture_rows = [
            {key: value for key, value in row.items() if key != "artifacts"} for row in rows
        ]
        self.assertEqual(report["coverage"], evaluate(plan, capture_rows))
        self.assertEqual(report["domain"], validate(plan, domain))
        self.assertEqual(report["methods"], methods_verify(plan, procedure, methods))
        self.assertEqual(
            report["captures"][0]["report"],
            verify(rows[0]["manifest"], rows[0]["artifacts"], now_ms=rows[0]["now_ms"]),
        )

    def test_maximum_payload_envelope_is_bounded_not_qualified(self):
        plan, rows, domain, procedure, _ = inputs()
        raw = rows[0]["manifest"]
        raw += b" " * (65536 - len(raw))
        payload = b"x" * 1048576
        full = [dict(rows[0], manifest=raw, artifacts={}) for _ in range(64)]
        for row in full[:4]:
            row["artifacts"] = {ABC: payload}
        methods = {f"{i:064x}": b" " * 65536 for i in range(48)}
        args = (
            plan + b" " * (65536 - len(plan)),
            full,
            domain + b" " * (65536 - len(domain)),
            procedure + b" " * (65536 - len(procedure)),
            methods,
        )
        report = self.evaluate(*args)
        self.assertEqual(len(report["captures"]), 64)
        self.assertEqual(report["methods"]["method_counts"]["supplied_bytes"], 3145728)
        self.assertFalse(report["software_checks_passed"])
        for index in (0, 2, 3):
            oversized = list(args)
            oversized[index] += b" "
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_assessment$"):
                self.evaluate(*oversized)


if __name__ == "__main__":
    unittest.main()
