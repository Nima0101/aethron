"""Bounded artifact negative-control review, with no device evidence."""

import hashlib
import io
import json
import platform
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qualification import artifacts
from qualification.technology.source_snapshot import capture, verify
from qualification.tests.test_artifact_review import ArtifactReviewTests
from qualification.tests.test_artifacts import ABC


def run_tests(name=None):
    suite = (
        unittest.TestSuite([ArtifactReviewTests(name)])
        if name
        else unittest.defaultTestLoader.loadTestsFromTestCase(ArtifactReviewTests)
    )
    return unittest.TextTestRunner(stream=io.StringIO()).run(suite)


def main():
    root = Path(__file__).parents[2]
    sources = capture(
        root,
        (
            "qualification/artifacts.py",
            "qualification/evidence.py",
            "aethron/_json_bounds.py",
            "qualification/tests/test_evidence.py",
            "qualification/tests/test_artifacts.py",
            "qualification/tests/test_artifact_review.py",
            "qualification/technology/review_artifacts.py",
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
        raise RuntimeError("artifact_review_failed")
    real_validate = artifacts.validate

    def erase_calibration(*args, **kwargs):
        report = real_validate(*args, **kwargs)
        report["findings"] = []
        report["declaration_checks_passed"] = True
        return report

    fake_hash = SimpleNamespace(sha256=lambda _: SimpleNamespace(hexdigest=lambda: ABC))
    mutations = {}
    cases = (
        (
            "constant_digest",
            "hashlib",
            fake_hash,
            "test_changed_supplied_mapping_requires_new_verification",
        ),
        (
            "erased_declaration_negatives",
            "validate",
            erase_calibration,
            "test_combined_failures_cannot_replace_declaration_negatives",
        ),
        (
            "relaxed_total_budget",
            "MAX_TOTAL_BYTES",
            4194305,
            "test_full_aggregate_budget_matches_four_distinct_contents",
        ),
    )
    for label, attribute, replacement, test in cases:
        with patch.object(artifacts, attribute, replacement):
            result = run_tests(test)
        if (
            not result.failures
            or result.errors
            or result.skipped
            or result.expectedFailures
            or result.unexpectedSuccesses
        ):
            raise RuntimeError("artifact_mutation_not_detected")
        mutations[label] = {"failures": len(result.failures), "errors": len(result.errors)}
    restored = run_tests()
    if (
        not restored.wasSuccessful()
        or not restored.testsRun
        or restored.skipped
        or restored.expectedFailures
    ):
        raise RuntimeError("artifact_review_restore_failed")
    verify(root, sources)
    print(
        json.dumps(
            {
                "review_order_version": 3,
                "component": "artifact_byte_binding",
                "python": platform.python_version(),
                "hash_backend_module": type(hashlib.sha256()).__module__,
                "baseline_tests": baseline.testsRun,
                "baseline_passed": True,
                "mutations": mutations,
                "restored_baseline_passed": True,
                "physical_qualification_passed": False,
                "source_sha256": sources,
                "source_observation": "equal_before_and_after_controls",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
