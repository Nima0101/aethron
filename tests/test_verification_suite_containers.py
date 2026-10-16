"""Inventory standard unittest containers by their constituent test cases."""

import subprocess
import unittest

from tests import test_verify_suite


class VerificationSuiteContainers(unittest.TestCase):
    fixture = test_verify_suite.VerificationSuite.fixture
    probe = test_verify_suite.VerificationSuite.probe
    assert_rejected = test_verify_suite.VerificationSuite.assert_rejected

    def test_nested_base_suites_and_repeated_cases_complete(self):
        for container in (
            "unittest.BaseTestSuite([case])",
            "unittest.TestSuite([unittest.BaseTestSuite([case, case])])",
            "unittest.BaseTestSuite([unittest.TestSuite([case]), unittest.BaseTestSuite([case])])",
            "unittest.TestSuite([unittest.BaseTestSuite(), case])",
        ):
            with self.subTest(container=container):
                result = self.probe(
                    "import unittest\n"
                    "class Case(unittest.TestCase):\n"
                    " def test_ok(self): self.assertEqual(2 + 2, 4)\n"
                    "def load_tests(loader, tests, pattern):\n"
                    " case = Case('test_ok')\n"
                    f" return {container}\n"
                )
                self.assertIsInstance(result, subprocess.CompletedProcess)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_nested_base_suites_preserve_skip_and_expected_failure(self):
        result = self.probe(
            "import unittest\n"
            "class Case(unittest.TestCase):\n"
            " @unittest.skip('platform unavailable')\n"
            " def test_skip(self): self.fail('must skip')\n"
            " @unittest.expectedFailure\n"
            " def test_known(self): self.fail('known')\n"
            "def load_tests(loader, tests, pattern):\n"
            " return unittest.TestSuite([unittest.BaseTestSuite([\n"
            "  Case('test_skip'), Case('test_known')])])\n"
        )
        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_base_suites_cannot_hide_failed_or_unexecuted_cases(self):
        for run in (
            "",
            " def run(self, result):\n  self._tests[0](result)\n  return result\n",
        ):
            with self.subTest(run=run):
                self.assert_rejected(
                    "import unittest\n"
                    "class Case(unittest.TestCase):\n"
                    " def test_ok(self): pass\n"
                    " def test_failure(self): self.fail('must execute')\n"
                    "class Suite(unittest.BaseTestSuite):\n"
                    " pass\n" + run + "def load_tests(loader, tests, pattern):\n"
                    " return unittest.TestSuite([Suite([\n"
                    "  Case('test_ok'), Case('test_failure')])])\n"
                )

    def test_empty_nested_base_suites_cannot_qualify(self):
        self.assert_rejected(
            "import unittest\n"
            "def load_tests(loader, tests, pattern):\n"
            " return unittest.TestSuite([unittest.BaseTestSuite()])\n"
        )


if __name__ == "__main__":
    unittest.main()
