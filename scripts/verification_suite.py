"""Run the trusted checkout suite without accepting absent or partial execution."""

import sys
import unittest
from pathlib import Path

# Test assertions are part of the evidence, even when the suite is invoked
# directly instead of through verify.py's own interpreter-mode preflight.
if sys.flags.optimize:
    raise SystemExit("verification_suite_requires_assertions")


def main():
    # Relative discovery and checkout imports must refer to this runner's tree.
    # Refuse another cwd before importing any tests, including direct invocations
    # that do not pass through verify.py's explicit child working directory.
    if Path.cwd().resolve() != Path(__file__).resolve().parents[1]:
        print("verification_suite_wrong_root", file=sys.stderr)
        return 1
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
