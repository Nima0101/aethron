"""Bounded SQL aggregation comparison; no physical or hard-real-time claims."""

import io
import json
import platform
import sqlite3
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.campaign import evaluate
from qualification.technology import campaign_sql, source_snapshot
from qualification.technology.measurement import peak_bytes, require_result, require_untraced
from qualification.tests.test_campaign import capture, plan_fixture
from qualification.tests.test_campaign_audit import CampaignAuditTests
from qualification.tests.test_evidence import encoded, fixture


def suite():
    return unittest.defaultTestLoader.loadTestsFromTestCase(CampaignAuditTests)


def main():
    require_untraced()
    root = Path(__file__).parents[2]
    sources = source_snapshot.capture(
        root,
        (
            "aethron/_json_bounds.py",
            "qualification/evidence.py",
            "qualification/campaign.py",
            "qualification/tests/test_evidence.py",
            "qualification/tests/test_campaign.py",
            "qualification/tests/test_campaign_audit.py",
            "qualification/technology/campaign_sql.py",
            "qualification/technology/compare_campaign.py",
            "qualification/technology/measurement.py",
            "qualification/technology/source_snapshot.py",
        ),
    )
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream)
    with patch.object(campaign_sql, "evaluate_sql", wraps=campaign_sql.evaluate_sql) as calls:
        result = runner.run(suite())
        invocations = calls.call_count
    if (
        not result.wasSuccessful()
        or not result.testsRun
        or result.skipped
        or result.expectedFailures
        or not invocations
    ):
        raise RuntimeError("campaign_candidate_contract_failed")
    # A relational mutant that admits all duplicate rows must be detected.
    with patch.object(
        campaign_sql, "ELIGIBLE", campaign_sql.ELIGIBLE.replace("d.n = 1", "d.n >= 1")
    ):
        mutant = runner.run(suite())
    if (
        not mutant.failures
        or mutant.errors
        or mutant.skipped
        or mutant.expectedFailures
        or mutant.unexpectedSuccesses
    ):
        raise RuntimeError("campaign_mutation_check_failed")
    plan = plan_fixture()
    plan["cases"] = [dict(plan["cases"][0], id=f"case{i}", minimum_captures=4) for i in range(16)]
    raw = encoded(plan)
    rows = [
        dict(capture(case_id=f"case{i // 4}"), manifest=encoded(fixture()) + b" " * i)
        for i in range(64)
    ]
    functions = {"python": evaluate, "sqlite": campaign_sql.evaluate_sql}
    samples = {name: [] for name in functions}
    # Fixed v1 workload oracle, not an answer supplied by either evaluator.
    # Commitments were independently reconstructed from explicit wire bytes.
    expected = {
        "version": 1,
        "plan_sha256": "e5d41a943710f3e18d879037e231fc7da7e378c3bea5cf3faa6664042ec90b9b",
        "captures_sha256": "9297849b54d145970ee979df3cb1b2aad5bd066352e8302d67c0d34a4c9f66e2",
        "capture_counts": {"submitted": 64, "eligible": 64, "rejected": 0},
        "cases": [{"case_index": i, "required": 4, "eligible": 4} for i in range(16)],
        "findings": [],
        "declaration_coverage_complete": True,
        "domain_verified": False,
        "procedure_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
    }
    for repetition in range(10):
        order = list(functions) if repetition % 2 else list(reversed(functions))
        for name in order:
            start = time.perf_counter_ns()
            actual = functions[name](raw, rows)
            samples[name].append(time.perf_counter_ns() - start)
            require_result(actual, expected, "campaign_maximum_parity_failed")
    allocations = {}
    for name, function in functions.items():
        traced_report = None

        def traced_call(function=function):
            nonlocal traced_report
            traced_report = function(raw, rows)

        allocations[name] = peak_bytes(traced_call)
        require_result(traced_report, expected, "campaign_maximum_parity_failed")
    source_snapshot.verify(root, sources)
    print(
        json.dumps(
            {
                "scope": "offline_campaign_aggregation_audit",
                "audit_policy_version": 3,
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "test_methods": result.testsRun,
                "candidate_calls": invocations,
                "all_contract_tests_passed": True,
                "duplicate_mutant_failures": len(mutant.failures),
                "duplicate_mutant_errors": len(mutant.errors),
                "maximum_cases": 16,
                "maximum_submissions": 64,
                "maximum_workload_report": expected,
                "maximum_result_oracle": "fixed_synthetic_v1",
                "all_measured_results_checked": True,
                "elapsed_ns": samples,
                "python_traced_peak_bytes": allocations,
                "measurement_limits": [
                    "Shared host, ten alternating-order repetitions; descriptive only.",
                    "Both paths share admission and declaration semantics; SQL aggregation is independent.",
                    "Tracing excludes preconstructed inputs and native SQLite allocations.",
                    "Result validation is outside measurements; traced calls retain their returned reports.",
                    "Whitespace-distinct bytes test input capacity, not independent physical evidence.",
                ],
                "source_sha256": sources,
                "source_observation": "equal_before_and_after_workload",
                "physical_qualification_passed": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
