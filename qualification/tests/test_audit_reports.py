"""Audit evidence must bind semantic dependencies and reject ambiguous responses."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.technology import compare_ingress, measure_binding


class AuditReportTests(unittest.TestCase):
    def responses(self):
        root = Path(compare_ingress.__file__).parent
        vectors = json.loads((root / "ingress-vectors-v1.json").read_text())
        rows = []
        for vector in vectors:
            raw = bytes.fromhex(vector["hex"])
            # A synthetic transport fixture, not evidence from a Java execution.
            if "error" in compare_ingress.outcome(raw, 1050):
                rows.append({"accepted": False})
            else:
                rows.append({"accepted": True, "document": json.loads(raw)})
        return rows

    def compare(self, lines):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "responses.jsonl"
            path.write_bytes(b"\n".join(lines) + b"\n")
            output = io.StringIO()
            with (
                patch("sys.argv", ["compare_ingress", "--responses", str(path)]),
                patch.object(compare_ingress, "collect", return_value=[]),
                contextlib.redirect_stdout(output),
            ):
                status = compare_ingress.main()
            return status, json.loads(output.getvalue())

    def lines(self, rows):
        return [json.dumps(row).encode() for row in rows]

    def assert_sources(self, report, required):
        root = Path(__file__).parents[2]
        self.assertTrue(required <= report["source_sha256"].keys())
        for name, digest in report["source_sha256"].items():
            self.assertEqual(digest, hashlib.sha256((root / name).read_bytes()).hexdigest())

    def test_ingress_report_binds_semantic_dependencies(self):
        status, report = self.compare(self.lines(self.responses()))
        self.assertEqual(status, 0)
        self.assertTrue(report["all_reports_match"])
        self.assert_sources(
            report,
            {
                "aethron/_json_bounds.py",
                "qualification/evidence.py",
                "qualification/rigs/synthetic-v1.json",
            },
        )

    def test_binding_report_binds_semantic_dependencies(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            measure_binding.main()
        report = json.loads(output.getvalue())
        self.assertEqual(report["artifact_counts"]["matched"], 4)
        self.assertIs(report["physical_qualification_passed"], False)
        self.assert_sources(
            report,
            {
                "aethron/_json_bounds.py",
                "qualification/evidence.py",
                "qualification/artifacts.py",
            },
        )

    def test_response_flag_requires_boolean(self):
        for flag in ("false", 1, None):
            with self.subTest(flag=flag):
                rows = self.responses()
                next(row for row in rows if row["accepted"])["accepted"] = flag
                with self.assertRaisesRegex(ValueError, "^invalid_audit_response$"):
                    self.compare(self.lines(rows))

    def test_response_envelope_is_unambiguous(self):
        rows = self.responses()
        index = next(i for i, row in enumerate(rows) if row["accepted"])
        for bad in (
            b'{"accepted":false,"accepted":true,"document":null}',
            b'{"accepted":false,"document":null}',
            b'{"accepted":false,"unknown":null}',
            b'{"accepted":true}',
            b'{"accepted":true,"document":NaN}',
            b'{"accepted":true,"document":{"a":1,"a":2}}',
            b"null",
            b"\xff",
        ):
            with self.subTest(bad=bad):
                lines = self.lines(rows)
                lines[index] = bad
                with self.assertRaisesRegex(ValueError, "^invalid_audit_response$"):
                    self.compare(lines)

    def test_always_rejecting_candidate_cannot_pass_comparison(self):
        rows = [{"accepted": False} for _ in self.responses()]
        status, report = self.compare(self.lines(rows))
        self.assertEqual(status, 1)
        self.assertFalse(report["all_reports_match"])
        self.assertGreater(len(report["mismatch_indices"]), 0)

    def test_missing_and_extra_response_rows_fail(self):
        lines = self.lines(self.responses())
        for invalid in (lines[:-1], lines + [b'{"accepted":false}']):
            with self.assertRaisesRegex(RuntimeError, "^audit_row_count$"):
                self.compare(invalid)

    def test_candidate_cannot_change_values_hidden_by_summary(self):
        for field, replacement in (("start_ms", 999), ("clock_domain", "other")):
            with self.subTest(field=field):
                rows = self.responses()
                rows[0]["document"]["capture"][field] = replacement
                status, report = self.compare(self.lines(rows))
                self.assertEqual(status, 1)
                self.assertEqual(report["document_mismatch_indices"], [0])
                self.assertTrue(report["all_reports_match"])
                self.assertFalse(report["all_documents_match"])

    def test_equal_rejection_outcomes_do_not_prove_document_fidelity(self):
        # Vector 3 has version 1.0. These replacements also fail the schema,
        # but none is the document the parser was asked to preserve.
        for replacement in (True, "1", None):
            with self.subTest(replacement=replacement):
                rows = self.responses()
                original = json.loads(
                    bytes.fromhex(
                        json.loads(
                            (
                                Path(compare_ingress.__file__).parent / "ingress-vectors-v1.json"
                            ).read_text()
                        )[3]["hex"]
                    )
                )
                original["version"] = replacement
                rows[3] = {"accepted": True, "document": original}
                status, report = self.compare(self.lines(rows))
                self.assertEqual(status, 1)
                self.assertEqual(report["document_mismatch_indices"], [3])

    def test_equal_schema_rejections_do_not_hide_forbidden_ingress_acceptance(self):
        vectors = json.loads(
            (Path(compare_ingress.__file__).parent / "ingress-vectors-v1.json").read_text()
        )
        # Preserve the decoded float exactly. Document and semantic comparisons
        # both match, but the ingress contract requires rejection of the token.
        for index in (3, 4, 5):
            with self.subTest(vector=vectors[index]["id"]):
                rows = self.responses()
                rows[index] = {
                    "accepted": True,
                    "document": json.loads(bytes.fromhex(vectors[index]["hex"])),
                }
                status, report = self.compare(self.lines(rows))
                self.assertEqual(status, 1)
                self.assertEqual(report["ingress_mismatch_indices"], [index])
                self.assertEqual(report["mismatch_indices"], [index])
                self.assertFalse(report["all_ingress_expectations_match"])
                self.assertTrue(report["all_reports_match"])
                self.assertTrue(report["all_documents_match"])

    def test_ingress_expectations_are_checked_in_both_directions(self):
        rows = self.responses()
        status, report = self.compare(self.lines(rows))
        self.assertEqual(status, 0)
        self.assertTrue(report["all_ingress_expectations_match"])
        self.assertEqual(report["ingress_mismatch_indices"], [])
        status, report = self.compare(self.lines([{"accepted": False} for _ in rows]))
        self.assertEqual(status, 1)
        self.assertFalse(report["all_ingress_expectations_match"])
        self.assertEqual(report["ingress_mismatch_indices"], [0, 1, 2])

    def test_accepting_malformed_source_cannot_hide_behind_schema_rejection(self):
        rows = self.responses()
        # Duplicate equal keys, invalid UTF-8, and malformed JSON respectively.
        for index in (9, 14, 17):
            with self.subTest(index=index):
                changed = list(rows)
                changed[index] = {"accepted": True, "document": None}
                status, report = self.compare(self.lines(changed))
                self.assertEqual(status, 1)
                self.assertEqual(report["document_mismatch_indices"], [index])

    def test_object_order_and_integer_negative_zero_preserve_documents(self):
        rows = self.responses()
        for row in rows:
            if row["accepted"]:
                row["document"] = dict(reversed(list(row["document"].items())))
        status, report = self.compare(self.lines(rows))
        self.assertEqual(status, 0)
        self.assertEqual(report["mismatch_indices"], [])
        self.assertTrue(report["all_documents_match"])


if __name__ == "__main__":
    unittest.main()
