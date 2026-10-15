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
        # TestSuite adds shared-fixture handling to BaseTestSuite. Both are
        # containers: counting either as a leaf misbinds completion callbacks.
        if isinstance(test, unittest.BaseTestSuite):
            yield from _cases(test)
        else:
            yield test


class _CompletionResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = Counter()
        self.stopped = Counter()
        self.pending = {}
        self.incomplete = False

    def startTest(self, test):
        if id(test) in self.pending:
            self.incomplete = True
        self.pending[id(test)] = False
        self.started[id(test)] += 1
        super().startTest(test)

    def stopTest(self, test):
        if not self.pending.pop(id(test), False):
            self.incomplete = True
        self.stopped[id(test)] += 1
        super().stopTest(test)

    def _outcome(self, test):
        if id(test) not in self.pending:
            self.incomplete = True
        else:
            self.pending[id(test)] = True

    def addSuccess(self, test):
        self._outcome(test)
        super().addSuccess(test)

    def addExpectedFailure(self, test, err):
        self._outcome(test)
        super().addExpectedFailure(test, err)

    def _report_problem(self, label, records):
        # The parent may terminate this process before unittest prints its
        # final report. Flush each observed problem now, including fixture and
        # subtest failures. Keep the ordinary final report and result lists:
        # early diagnostics must not change acceptance or completion accounting.
        self.stream.writeln()
        self.printErrorList(label, records[-1:])
        self.stream.flush()

    def addError(self, test, err):
        super().addError(test, err)
        self._report_problem("ERROR", self.errors)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._report_problem("FAIL", self.failures)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            if issubclass(err[0], test.failureException):
                self._report_problem("FAIL", self.failures)
            else:
                self._report_problem("ERROR", self.errors)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.stream.writeln()
        self.stream.writeln("UNEXPECTED SUCCESS: " + self.getDescription(test))
        self.stream.flush()

    def addSkip(self, test, reason):
        if isinstance(test, unittest.TestCase):
            # unittest reports skipped subtests using a child TestCase whose
            # test_case points to the running parent, with no parent success
            # callback. Multiple subtest skips still cover only this execution.
            parent = test if id(test) in self.pending else getattr(test, "test_case", test)
            self._outcome(parent)
        # Shared-fixture holders have no start/stop pair; _completed accounts
        # for their setup skips. Failures/errors already reject via wasSuccessful.
        super().addSkip(test, reason)


def _completed(cases, discovered, result):
    expected = Counter(id(test) for test in cases)
    if (
        result.incomplete
        or result.pending
        or discovered != len(cases)
        or result.testsRun != sum(result.started.values())
        # Custom run hooks can return after startTest without completing the
        # lifecycle. Aggregate totals alone also miss stops for another case.
        or result.started != result.stopped
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
