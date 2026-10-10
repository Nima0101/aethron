"""Finite campaign aggregation controls; no physical qualification."""

import hashlib
import io
import json
import platform
import sqlite3
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from qualification import campaign
from qualification.technology import campaign_sql
from qualification.tests.test_campaign_review import CampaignReviewTests


def run_tests():
    return unittest.TextTestRunner(stream=io.StringIO()).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CampaignReviewTests)
    )


def main():
    baseline = run_tests()
    if not baseline.wasSuccessful() or baseline.skipped:
        raise RuntimeError("campaign_review_failed")

    def single_counts(values):
        return Counter(set(values))

    def unique_bindings(values):
        ordered = sorted(values)
        return list(dict.fromkeys(ordered)) if ordered and type(ordered[0]) is tuple else ordered

    mutations = {}
    controls = (
        ("duplicate_counts_erased", patch.object(campaign, "Counter", single_counts)),
        (
            "commitment_multiplicity_erased",
            patch.object(campaign, "sorted", unique_bindings, create=True),
        ),
        (
            "sql_duplicates_admitted",
            patch.object(
                campaign_sql, "ELIGIBLE", campaign_sql.ELIGIBLE.replace("d.n = 1", "d.n >= 1")
            ),
        ),
    )
    for name, control in controls:
        with control:
            result = run_tests()
        if result.wasSuccessful() or result.errors or result.skipped:
            raise RuntimeError("campaign_mutation_not_detected")
        mutations[name] = {"failures": len(result.failures), "errors": len(result.errors)}
    restored = run_tests()
    if not restored.wasSuccessful() or restored.skipped:
        raise RuntimeError("campaign_review_restore_failed")
    root = Path(__file__).parents[2]
    print(
        json.dumps(
            {
                "review_order_version": 3,
                "component": "campaign_coverage_and_procedures",
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "baseline_tests": baseline.testsRun,
                "baseline_passed": True,
                "mutations": mutations,
                "restored_baseline_passed": True,
                "limits": [
                    "SQL aggregation is independent; admission and capture semantics are shared.",
                    "Finite synthetic controls do not demonstrate scientific sample independence.",
                    "No authenticated preregistration, clock, procedure or domain evidence.",
                ],
                "physical_qualification_passed": False,
                "source_sha256": {
                    name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                    for name in (
                        "aethron/_json_bounds.py",
                        "qualification/evidence.py",
                        "qualification/campaign.py",
                        "qualification/technology/campaign_sql.py",
                        "qualification/tests/test_evidence.py",
                        "qualification/tests/test_campaign.py",
                        "qualification/tests/test_campaign_review.py",
                        "qualification/technology/review_campaign.py",
                    )
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
