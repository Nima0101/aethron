"""Fixture skips must account only for their own discovered test cases."""

import subprocess
import unittest

from tests import test_verify_suite


class VerificationFixtureSkips(unittest.TestCase):
    fixture = test_verify_suite.VerificationSuite.fixture
    probe = test_verify_suite.VerificationSuite.probe
    assert_rejected = test_verify_suite.VerificationSuite.assert_rejected

    cases = (
        "class Case(unittest.TestCase):\n"
        " def test_one(self): self.fail('fixture should skip')\n"
        " def test_two(self): self.fail('fixture should skip')\n"
    )

    def assert_accepted(self, source):
        result = self.probe(source)
        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipped=", result.stderr)
        self.assertNotIn("verification_suite_incomplete", result.stderr)

    def test_setup_class_skip_accounts_for_all_class_cases(self):
        for extra in ("", "class Other(unittest.TestCase):\n def test_ok(self): pass\n"):
            with self.subTest(extra=extra):
                self.assert_accepted(
                    "import unittest\n" + self.cases + " @classmethod\n"
                    " def setUpClass(cls): raise unittest.SkipTest('platform unavailable')\n"
                    + extra
                )

    def test_setup_module_skip_accounts_for_multiple_classes(self):
        self.assert_accepted(
            "import unittest\n"
            "def setUpModule(): raise unittest.SkipTest('platform unavailable')\n"
            + self.cases
            + "class Other(unittest.TestCase):\n"
            " def test_three(self): self.fail('module should skip')\n"
        )

    def test_fixture_skip_does_not_cover_unexecuted_other_class(self):
        self.assert_rejected(
            "import unittest\n" + self.cases + " @classmethod\n"
            " def setUpClass(cls): raise unittest.SkipTest('platform unavailable')\n"
            "class Other(unittest.TestCase):\n"
            " def test_missing(self): self.fail('must run')\n"
            "class Partial(unittest.TestSuite):\n"
            " def run(self, result, debug=False):\n"
            "  unittest.TestSuite([Case('test_one'), Case('test_two')]).run(result)\n"
            "  return result\n"
            "def load_tests(loader, tests, pattern):\n"
            " return Partial([Case('test_one'), Case('test_two'), Other('test_missing')])\n"
        )

    def test_teardown_skips_do_not_cover_missing_tests(self):
        for fixture in (
            "class Case(unittest.TestCase):\n"
            " @classmethod\n"
            " def tearDownClass(cls): raise unittest.SkipTest('cleanup unavailable')\n",
            "def tearDownModule(): raise unittest.SkipTest('cleanup unavailable')\n"
            "class Case(unittest.TestCase):\n",
        ):
            with self.subTest(fixture=fixture):
                self.assert_rejected(
                    "import unittest\n" + fixture + " def test_one(self): pass\n"
                    " def test_missing(self): self.fail('must run')\n"
                    "class Partial(unittest.TestSuite):\n"
                    " def run(self, result, debug=False):\n"
                    "  unittest.TestSuite([self._tests[0]]).run(result)\n"
                    "  return result\n"
                    "def load_tests(loader, tests, pattern):\n"
                    " return Partial([Case('test_one'), Case('test_missing')])\n"
                )

    def test_module_skip_does_not_cover_unexecuted_other_module(self):
        self.assert_rejected(
            "import unittest\n"
            "def setUpModule(): raise unittest.SkipTest('platform unavailable')\n"
            + self.cases
            + "class Other(unittest.TestCase):\n"
            " __module__ = 'other_fixture'\n"
            " def test_missing(self): self.fail('must run')\n"
            "class Partial(unittest.TestSuite):\n"
            " def run(self, result, debug=False):\n"
            "  unittest.TestSuite([self._tests[0]]).run(result)\n"
            "  return result\n"
            "def load_tests(loader, tests, pattern):\n"
            " return Partial([Case('test_one'), Case('test_two'), Other('test_missing')])\n"
        )

    def test_fixture_errors_and_other_failures_remain_failures(self):
        for body in (
            "def setUpModule(): raise RuntimeError('broken fixture')\n" + self.cases,
            self.cases + " @classmethod\n def setUpClass(cls): raise RuntimeError('broken')\n",
            self.cases + " @classmethod\n"
            " def setUpClass(cls): raise unittest.SkipTest('platform unavailable')\n"
            "class Other(unittest.TestCase):\n def test_bad(self): self.fail('must fail')\n",
        ):
            with self.subTest(body=body):
                self.assert_rejected("import unittest\n" + body)


if __name__ == "__main__":
    unittest.main()
