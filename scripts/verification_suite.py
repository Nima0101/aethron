"""Run the trusted checkout suite without accepting absent or partial execution."""

import sys
import unittest


def main():
    loader = unittest.TestLoader()
    try:
        suite = loader.discover("tests")
        discovered = suite.countTestCases()
        result = unittest.TextTestRunner().run(suite)
    except SystemExit:
        # A discovery/count/run hook exiting zero has not completed the gate.
        print("verification_suite_incomplete", file=sys.stderr)
        return 1
    # Preserve unittest's existing platform-skip/expected-failure semantics.
    # Completion counts are evidence for trusted tests, not a test-code sandbox.
    accepted = (
        discovered > 0
        and result.testsRun == discovered
        and result.wasSuccessful()
        and not loader.errors
    )
    if not accepted:
        print("verification_suite_incomplete", file=sys.stderr)
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
