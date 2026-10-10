"""Comparison output must reject changing checkout source observations."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.technology import compare_campaign, compare_ingress, measure_binding

MODES = (
    (measure_binding, "fixture", False),
    (compare_campaign, "suite", False),
    (compare_ingress, "collect", False),
    (compare_ingress, "collect", True),
)


def ingress_responses():
    """Synthetic Python responses only; this does not execute a Java parser."""
    root = Path(compare_ingress.__file__).parent
    vectors = json.loads((root / "ingress-vectors-v1.json").read_text())
    requests = [(bytes.fromhex(row["hex"]), 1050) for row in vectors] + compare_ingress.collect()
    rows = []
    for raw, now in requests:
        row = {"accepted": False}
        if "error" not in compare_ingress.outcome(raw, now):
            row = {"accepted": True, "document": json.loads(raw)}
        rows.append(json.dumps(row).encode())
    return b"\n".join(rows) + b"\n"


class ComparisonSourceTests(unittest.TestCase):
    def exercise(self, module, entry, export, fault):
        read = Path.read_bytes
        original = getattr(module, entry)
        state = {"work": 0}
        target = Path(__file__).parents[2] / "qualification/evidence.py"

        def observed_bytes(path):
            if path == target:
                if fault == "missing_before" or (fault == "missing_after" and state["work"]):
                    raise OSError("PRIVATE source unavailable")
                if fault == "changed" and state["work"]:
                    return read(path) + b"\n# changed after workload admission\n"
            return read(path)

        def workload(*args, **kwargs):
            result = original(*args, **kwargs)
            state["work"] += 1
            return result

        output, error, status = io.StringIO(), None, None
        with tempfile.TemporaryDirectory() as folder:
            response = Path(folder) / "synthetic.jsonl"
            argv = [module.__name__]
            if module is compare_ingress:
                if export:
                    argv += ["--export"]
                else:
                    response.write_bytes(ingress_responses())
                    argv += ["--responses", str(response)]
            with (
                patch("sys.argv", argv),
                patch.object(Path, "read_bytes", observed_bytes),
                patch.object(module, entry, workload),
                contextlib.redirect_stdout(output),
            ):
                try:
                    status = module.main()
                except (RuntimeError, OSError) as caught:
                    error = caught
        return error, output.getvalue(), state["work"], status

    def test_changed_sources_prevent_reports_and_export(self):
        for mode in MODES:
            with self.subTest(module=mode[0].__name__, export=mode[2]):
                error, output, work, _ = self.exercise(*mode, "changed")
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), "review_sources_changed")
                self.assertEqual(output, "")
                self.assertGreater(work, 0)

    def test_unreadable_initial_sources_prevent_workload(self):
        for mode in MODES:
            with self.subTest(module=mode[0].__name__, export=mode[2]):
                error, output, work, _ = self.exercise(*mode, "missing_before")
                self.assertEqual(work, 0)
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), "review_sources_unavailable")
                self.assertEqual(output, "")

    def test_unreadable_final_sources_prevent_output(self):
        for mode in MODES:
            with self.subTest(module=mode[0].__name__, export=mode[2]):
                error, output, work, _ = self.exercise(*mode, "missing_after")
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), "review_sources_unavailable")
                self.assertEqual(output, "")
                self.assertGreater(work, 0)

    def test_stable_sources_preserve_reports_and_transport(self):
        root = Path(__file__).parents[2]
        for mode in MODES:
            with self.subTest(module=mode[0].__name__, export=mode[2]):
                error, output, work, status = self.exercise(*mode, None)
                self.assertIsNone(error)
                self.assertGreater(work, 0)
                if mode[2]:
                    vectors = json.loads(
                        (root / "qualification/technology/ingress-vectors-v1.json").read_text()
                    )
                    expected = [row["hex"] for row in vectors]
                    expected += [raw.hex() for raw, _ in compare_ingress.collect()]
                    self.assertEqual(output, "\n".join(expected) + "\n")
                    self.assertEqual(status, 0)
                    continue
                report = json.loads(output)
                self.assertEqual(
                    report.get("source_observation"), "equal_before_and_after_workload"
                )
                sources = report["source_sha256"]
                self.assertIn("qualification/technology/source_snapshot.py", sources)
                for name, digest in sources.items():
                    self.assertEqual(digest, hashlib.sha256((root / name).read_bytes()).hexdigest())
                self.assertIs(report["physical_qualification_passed"], False)
                if mode[0] is compare_ingress:
                    self.assertEqual(status, 0)
                    self.assertEqual(report["mismatch_indices"], [])
                elif mode[0] is compare_campaign:
                    self.assertGreater(report["candidate_calls"], 0)
                    self.assertGreater(report["duplicate_mutant_failures"], 0)
                else:
                    self.assertEqual(report["artifact_counts"]["matched"], 4)
