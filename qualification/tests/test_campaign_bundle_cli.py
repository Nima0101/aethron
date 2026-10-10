"""Stream framing must preserve bytes, limits, negative evidence and exit status."""

import contextlib
import hashlib
import importlib.util
import io
import json
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qualification.tests.test_campaign import capture
from qualification.tests.test_campaign_references import reference_plan

MAGIC = b"AETHRON-QUALIFICATION-BUNDLE-V1\n"


def blob(raw):
    return struct.pack(">I", len(raw)) + raw


def frame(plan=None, rows=None, domain=b"abc", procedure=b"def"):
    plan = reference_plan(domain, procedure) if plan is None else plan
    rows = [capture()] if rows is None else rows
    parts = [MAGIC, blob(plan), blob(domain), blob(procedure), struct.pack(">I", len(rows))]
    for row in rows:
        parts += [
            blob(row["case_id"].encode("ascii")),
            struct.pack(">Q", row["now_ms"]),
            blob(row["manifest"]),
        ]
    return b"".join(parts)


class ShortReads(io.BytesIO):
    def read(self, size=-1):
        if size < 0:
            raise AssertionError("unbounded read")
        return super().read(min(size, 3))


class NoReadPastHeader(io.BytesIO):
    def read(self, size=-1):
        if size < 0 or self.tell() == len(self.getvalue()):
            raise AssertionError("payload read after forbidden length")
        return super().read(size)


class CampaignBundleCliTests(unittest.TestCase):
    def invoke(self, raw, args=()):
        self.assertIsNotNone(importlib.util.find_spec("qualification.campaign_bundle_cli"))
        from qualification.campaign_bundle_cli import main

        source = io.BytesIO(raw) if type(raw) is bytes else raw
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["campaign_bundle_cli", *args]),
            patch.object(sys, "stdin", SimpleNamespace(buffer=source)),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = main()
        return code, out.getvalue(), err.getvalue()

    def test_positive_report_preserves_exact_plan_and_capture_bytes(self):
        plan = reference_plan() + b" \n"
        row = capture()
        row["manifest"] += b" \n"
        code, out, err = self.invoke(frame(plan, [row]))
        self.assertEqual((code, err), (0, ""))
        report = json.loads(out)
        digest = hashlib.sha256(plan).hexdigest()
        for nested in (report, report["coverage"], report["references"]):
            self.assertEqual(nested["plan_sha256"], digest)
            self.assertIs(nested["physical_qualification_passed"], False)
        bindings = [["blackout", hashlib.sha256(row["manifest"]).hexdigest(), 1050]]
        self.assertEqual(
            report["coverage"]["captures_sha256"],
            hashlib.sha256(
                b"aethron.qualification.captures.v1\0"
                + json.dumps(bindings, separators=(",", ":")).encode()
            ).hexdigest(),
        )
        self.assertIs(report["software_checks_passed"], True)
        self.assertEqual(
            report["coverage"]["capture_counts"], {"submitted": 1, "eligible": 1, "rejected": 0}
        )
        self.assertEqual(
            report["references"]["reference_counts"],
            {"supplied": 2, "matched": 2, "supplied_bytes": 6},
        )
        self.assertEqual(out, json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")

    def test_negative_report_retains_coverage_and_reference_failures(self):
        code, out, err = self.invoke(
            frame(reference_plan(), [capture(), capture()], b"bad", b"bad")
        )
        self.assertEqual((code, err), (1, ""))
        report = json.loads(out)
        self.assertIs(report["software_checks_passed"], False)
        self.assertEqual(
            report["coverage"]["findings"], ["capture_coverage_missing", "capture_reused"]
        )
        self.assertEqual(
            report["references"]["reference_findings"],
            ["domain_digest_mismatch", "procedure_digest_mismatch"],
        )

    def test_short_reads_do_not_change_the_report(self):
        raw = frame()
        expected = self.invoke(raw)
        self.assertEqual(expected[0], 0)
        self.assertEqual(self.invoke(ShortReads(raw)), expected)

    def test_truncated_or_trailing_frames_never_emit_a_report(self):
        raw = frame()
        # Every prefix of a small valid frame, including all field/payload boundaries.
        for length in range(len(raw)):
            with self.subTest(length=length):
                self.assertEqual(self.invoke(raw[:length]), (2, "", "invalid_campaign_bundle\n"))
        for malformed in (raw + b"\0", raw + raw, b"?" + raw[1:]):
            with self.subTest(size=len(malformed)):
                self.assertEqual(self.invoke(malformed), (2, "", "invalid_campaign_bundle\n"))

    def test_oversized_lengths_are_rejected_before_payload_reads(self):
        plan = blob(reference_plan())
        domain, procedure = blob(b"abc"), blob(b"def")
        prefix = MAGIC + plan + domain + procedure
        for header in (
            MAGIC + struct.pack(">I", 65537),
            MAGIC + plan + struct.pack(">I", 1048577),
            MAGIC + plan + domain + struct.pack(">I", 1048577),
            prefix + struct.pack(">I", 65),
            prefix + struct.pack(">II", 1, 65),
            prefix + struct.pack(">I", 1) + blob(b"blackout") + struct.pack(">QI", 1050, 65537),
            MAGIC + b"\xff" * 4,
        ):
            with self.subTest(header=header[-12:]):
                self.assertEqual(
                    self.invoke(NoReadPastHeader(header)), (2, "", "invalid_campaign_bundle\n")
                )

    def test_invalid_names_instants_plans_and_arguments_have_fixed_errors(self):
        prefix = MAGIC + blob(reference_plan()) + blob(b"abc") + blob(b"def")
        for raw in (
            frame(b'{"PRIVATE":'),
            frame(rows=[dict(capture(), now_ms=2**64 - 1)]),
            frame(rows=[dict(capture(), case_id="PRIVATE name")]),
            prefix
            + struct.pack(">I", 1)
            + blob(b"\xff")
            + struct.pack(">Q", 1050)
            + blob(capture()["manifest"]),
        ):
            with self.subTest(size=len(raw)):
                self.assertEqual(self.invoke(raw), (2, "", "invalid_campaign_bundle\n"))
        self.assertEqual(self.invoke(frame(), ["--PRIVATE"]), (2, "", "invalid_campaign_bundle\n"))

    def test_empty_capture_list_is_a_negative_report(self):
        code, out, err = self.invoke(frame(rows=[]))
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(
            json.loads(out)["coverage"]["capture_counts"],
            {"submitted": 0, "eligible": 0, "rejected": 0},
        )

    def test_reference_limits_and_opaque_bytes_are_usable(self):
        for domain, procedure in ((b"", b""), (b"\xff" * 1048576, b"\0" * 1048576)):
            code, out, err = self.invoke(frame(domain=domain, procedure=procedure))
            self.assertEqual((code, err), (0, ""))
            self.assertIs(json.loads(out)["physical_qualification_passed"], False)

    def test_read_errors_do_not_disclose_private_exception_text(self):
        class BrokenInput:
            def read(self, size):
                raise OSError("PRIVATE device path")

        self.assertEqual(self.invoke(BrokenInput()), (2, "", "invalid_campaign_bundle\n"))

    def test_golden_report_bytes(self):
        golden = Path(__file__).parents[1] / "evidence/synthetic-campaign-bundle-v1.json"
        self.assertTrue(golden.is_file())
        self.assertEqual(self.invoke(frame()), (0, golden.read_text(), ""))

    def test_exact_capture_and_manifest_limits_are_usable(self):
        row = capture()
        rows = [
            dict(row, manifest=row["manifest"] + b" " * (65536 - len(row["manifest"]) - i))
            for i in range(64)
        ]
        code, out, err = self.invoke(frame(rows=rows))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(
            json.loads(out)["coverage"]["capture_counts"],
            {"submitted": 64, "eligible": 64, "rejected": 0},
        )


if __name__ == "__main__":
    unittest.main()
