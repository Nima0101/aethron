"""Bounded audit harness checks; no network, vehicle, or simulator access."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


class WireAuditTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/robotics_wire_audit_v2.py"
        self.assertTrue(path.is_file(), "missing executable technology comparison")
        spec = importlib.util.spec_from_file_location("wire_audit", path)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)

    def test_corpus_covers_both_layouts_and_wire_rejections(self):
        cases = self.api.corpus()
        self.assertGreaterEqual(len(cases), 12)
        self.assertLessEqual(len(cases), 32)
        self.assertEqual(len({case["name"] for case in cases}), len(cases))
        for case in cases:
            with self.subTest(name=case["name"]):
                result = self.api.python_result(bytes.fromhex(case["hex"]))
                self.assertEqual(result["accepted"], case["accepted"])
        self.assertEqual({case["message"] for case in cases if case["accepted"]}, {30, 32})

    def test_parity_rejects_disagreeing_admission_or_numeric_values(self):
        expected = [{"accepted": True, "message": 30, "boot": 10, "values": [0.1] * 6}]
        self.api.check_parity(expected, expected)
        for wrong in ([{"accepted": False}], [], [dict(expected[0], values=[1.0] * 6)]):
            with self.assertRaisesRegex(ValueError, "candidate_parity_failed"):
                self.api.check_parity(expected, wrong)

    def test_existing_output_is_refused_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "result.json").write_text("prior negative evidence")
            with self.assertRaises(FileExistsError):
                self.api.run(out)
            self.assertEqual((out / "result.json").read_text(), "prior negative evidence")


if __name__ == "__main__":
    unittest.main()
