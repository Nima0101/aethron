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
    root = Path(__file__).resolve().parents[1]
    if Path.cwd().resolve() != root:
        print("verification_suite_wrong_root", file=sys.stderr)
        return 1
    # Script entry starts with scripts/ on sys.path, unlike module entry. Put
    # checkout packages before foreign PYTHONPATH/installed copies in both modes.
    # This is import precedence for trusted tests, not interpreter isolation.
    sys.path.insert(0, str(root))
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
