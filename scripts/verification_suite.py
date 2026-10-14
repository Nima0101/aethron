"""Run the trusted checkout suite without accepting absent or partial execution."""

import sys
import unittest
from collections import Counter
from pathlib import Path

# Test assertions are part of the evidence, even when the suite is invoked
# directly instead of through verify.py's own interpreter-mode preflight.
if sys.flags.optimize:
    raise SystemExit("verification_suite_requires_assertions")


def _cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _cases(test)
        else:
            yield test


class _CompletionResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = Counter()

    def startTest(self, test):
        self.started[id(test)] += 1
        super().startTest(test)


def _completed(cases, discovered, result):
    expected = Counter(id(test) for test in cases)
    if (
        discovered != len(cases)
        or result.testsRun != sum(result.started.values())
        or result.started - expected
    ):
        return False
    # unittest reports a shared-fixture skip through a synthetic result holder,
    # without starting its test cases. Match only setup labels to the original
    # discovered classes/modules; teardown skips cannot cover unfinished tests.
    # Unknown fixture labels fail closed. This is trusted-suite accounting, not
    # protection against tests deliberately forging their result callbacks.
    skipped = {test.id() for test, _ in result.skipped if not isinstance(test, unittest.TestCase)}
    remaining = expected - result.started
    for test in cases:
        cls = type(test)
        if remaining[id(test)] and not skipped.intersection(
            (f"setUpClass ({cls.__module__}.{cls.__qualname__})", f"setUpModule ({cls.__module__})")
        ):
            return False
    return True


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
        cases = list(_cases(suite))
        result = unittest.TextTestRunner(resultclass=_CompletionResult).run(suite)
    except SystemExit:
        # A discovery/count/run hook exiting zero has not completed the gate.
        print("verification_suite_incomplete", file=sys.stderr)
        return 1
    # Preserve unittest's existing platform-skip/expected-failure semantics.
    # Completion counts are evidence for trusted tests, not a test-code sandbox.
    accepted = (
        discovered > 0
        and _completed(cases, discovered, result)
        and result.wasSuccessful()
        and not loader.errors
    )
    if not accepted:
        print("verification_suite_incomplete", file=sys.stderr)
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
