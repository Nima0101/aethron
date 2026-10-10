"""Fresh bounded declaration review, including negative-finding mutations."""

import io
import json
import platform
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification import evidence
from qualification.technology.source_snapshot import capture, verify
from qualification.tests.test_declaration_review import DeclarationReviewTests


def run_tests():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DeclarationReviewTests)
    return unittest.TextTestRunner(stream=io.StringIO()).run(suite)


def main():
    root = Path(__file__).parents[2]
    sources = capture(
        root,
        (
            "aethron/_json_bounds.py",
            "qualification/evidence.py",
            "qualification/tests/test_evidence.py",
            "qualification/tests/test_declaration_review.py",
            "qualification/technology/review_declarations.py",
            "qualification/technology/source_snapshot.py",
        ),
    )
    baseline = run_tests()
    if (
        not baseline.wasSuccessful()
        or not baseline.testsRun
        or baseline.skipped
        or baseline.expectedFailures
    ):
        raise RuntimeError("declaration_review_failed")
    original = evidence._findings
    mutants = {}
    for dropped in (
        "capture_stale",
        "record_stale",
        "clock_pair_skew",
        "clock_domain_mismatch",
    ):

        def omit_finding(doc, now_ms, code=dropped):
            return [finding for finding in original(doc, now_ms) if finding != code]

        with patch.object(evidence, "_findings", omit_finding):
            result = run_tests()
        if (
            not result.failures
            or result.errors
            or result.skipped
            or result.expectedFailures
            or result.unexpectedSuccesses
        ):
            raise RuntimeError("declaration_review_mutation_not_detected")
        mutants[dropped] = {"failures": len(result.failures), "errors": len(result.errors)}
    restored = run_tests()
    if (
        not restored.wasSuccessful()
        or not restored.testsRun
        or restored.skipped
        or restored.expectedFailures
    ):
        raise RuntimeError("declaration_review_restore_failed")
    verify(root, sources)
    print(
        json.dumps(
            {
                "review_order_version": 3,
                "component": "declaration_validation",
                "python": platform.python_version(),
                "baseline_tests": baseline.testsRun,
                "baseline_passed": True,
                "negative_finding_mutations": mutants,
                "restored_baseline_passed": True,
                "scope": "synthetic offline declarations; not live admission or authentication",
                "physical_qualification_passed": False,
                "source_sha256": sources,
                "source_observation": "equal_before_and_after_controls",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
