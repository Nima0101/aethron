"""A completed callback pair must include an outcome for that execution."""

import subprocess
import unittest

from tests import test_verify_suite


class VerificationSuiteOutcomes(unittest.TestCase):
    fixture = test_verify_suite.VerificationSuite.fixture
    probe = test_verify_suite.VerificationSuite.probe
    assert_rejected = test_verify_suite.VerificationSuite.assert_rejected

    def test_missing_or_foreign_outcome_cannot_qualify(self):
        for outcome in ("", "  result.addSuccess(Case('test_missing'))\n"):
            with self.subTest(outcome=outcome):
                self.assert_rejected(
                    "import unittest\n"
                    "class Case(unittest.TestCase):\n"
                    " def test_missing(self): self.fail('must execute')\n"
                    " def run(self, result):\n"
                    "  result.startTest(self)\n" + outcome + "  result.stopTest(self)\n"
                    "  return result\n"
                )

    def test_previous_execution_outcome_cannot_cover_missing_outcome(self):
        for outcome in (
            "result.addSuccess(self)",
            "result.addSkip(self, 'platform unavailable')",
        ):
            with self.subTest(outcome=outcome):
                self.assert_rejected(
                    "import unittest\n"
                    "class Case(unittest.TestCase):\n"
                    " runs = 0\n"
                    " def test_missing(self): self.fail('must execute')\n"
                    " def run(self, result):\n"
                    "  result.startTest(self)\n"
                    f"  if self.runs == 0: {outcome}\n"
                    "  self.runs += 1\n"
                    "  result.stopTest(self)\n"
                    "  return result\n"
                    "def load_tests(loader, tests, pattern):\n"
                    " case = Case('test_missing')\n"
                    " return unittest.TestSuite([case, case])\n"
                )

    def test_outcome_after_stop_cannot_repair_incomplete_execution(self):
        self.assert_rejected(
            "import unittest\n"
            "class Case(unittest.TestCase):\n"
            " def test_missing(self): self.fail('must execute')\n"
            " def run(self, result):\n"
            "  result.startTest(self)\n"
            "  result.stopTest(self)\n"
            "  result.addSuccess(self)\n"
            "  return result\n"
        )

    def test_subtests_skips_and_expected_failures_remain_supported(self):
        for body in (
            " def test_ok(self):\n"
            "  for value in (1, 2):\n"
            "   with self.subTest(value=value): self.assertGreater(value, 0)\n",
            " def test_ok(self):\n"
            "  for value in (1, 2):\n"
            "   with self.subTest(value=value): self.skipTest('unavailable')\n",
            " def test_ok(self):\n"
            "  with self.subTest(outer=1):\n"
            "   with self.subTest(inner=2): self.skipTest('unavailable')\n"
            "  with self.subTest(outer=2): self.assertTrue(True)\n",
            " def setUp(self): self.skipTest('unavailable')\n"
            " def test_ok(self): self.fail('must skip')\n",
            " @unittest.expectedFailure\n def test_ok(self): self.fail('known')\n",
        ):
            with self.subTest(body=body):
                result = self.probe(
                    "import unittest\nclass Case(unittest.TestCase):\n"
                    + body
                    + "def load_tests(loader, tests, pattern):\n"
                    " case = Case('test_ok')\n"
                    " return unittest.TestSuite([case, case])\n"
                )
                self.assertIsInstance(result, subprocess.CompletedProcess)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
