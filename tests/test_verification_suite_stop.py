"""A started test is not evidence of a completed test lifecycle."""

import subprocess
import unittest

from tests import test_verify_suite


class VerificationSuiteStop(unittest.TestCase):
    fixture = test_verify_suite.VerificationSuite.fixture
    probe = test_verify_suite.VerificationSuite.probe
    assert_rejected = test_verify_suite.VerificationSuite.assert_rejected

    def test_started_test_without_stop_cannot_qualify(self):
        for outcome in ("", "  result.addSuccess(self)\n"):
            with self.subTest(outcome=outcome):
                self.assert_rejected(
                    "import unittest\n"
                    "class Case(unittest.TestCase):\n"
                    " def test_missing(self): self.fail('must execute')\n"
                    " def run(self, result):\n"
                    "  result.startTest(self)\n" + outcome + "  return result\n"
                )

    def test_stops_must_match_the_started_case(self):
        for stops in (
            "  result.stopTest(Case('test_missing'))\n",
            "  result.stopTest(self)\n  result.stopTest(self)\n",
        ):
            with self.subTest(stops=stops):
                self.assert_rejected(
                    "import unittest\n"
                    "class Case(unittest.TestCase):\n"
                    " def test_missing(self): self.fail('must execute')\n"
                    " def run(self, result):\n"
                    "  result.startTest(self)\n"
                    "  result.addSuccess(self)\n" + stops + "  return result\n"
                )

    def test_complete_custom_run_and_repeated_instances_remain_supported(self):
        base = (
            "import unittest\n"
            "class Case(unittest.TestCase):\n"
            " def test_ok(self): self.assertEqual(2 + 2, 4)\n"
            " def run(self, result): return super().run(result)\n"
        )
        for hook in (
            "",
            "def load_tests(loader, tests, pattern):\n"
            " case = Case('test_ok')\n"
            " return unittest.TestSuite([case, case])\n",
        ):
            with self.subTest(hook=hook):
                result = self.probe(base + hook)
                self.assertIsInstance(result, subprocess.CompletedProcess)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
