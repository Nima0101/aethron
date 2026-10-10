"""Bounded SQL aggregation comparison; no physical or hard-real-time claims."""

import hashlib
import io
import json
import platform
import sqlite3
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.campaign import evaluate
from qualification.technology import campaign_sql
from qualification.tests.test_campaign import capture, plan_fixture
from qualification.tests.test_campaign_audit import CampaignAuditTests
from qualification.tests.test_evidence import encoded, fixture


def suite():
    return unittest.defaultTestLoader.loadTestsFromTestCase(CampaignAuditTests)


def main():
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream)
    with patch.object(campaign_sql, "evaluate_sql", wraps=campaign_sql.evaluate_sql) as calls:
        result = runner.run(suite())
        invocations = calls.call_count
    if not result.wasSuccessful():
        raise RuntimeError("campaign_candidate_contract_failed")
    # A relational mutant that admits all duplicate rows must be detected.
    with patch.object(
        campaign_sql, "ELIGIBLE", campaign_sql.ELIGIBLE.replace("d.n = 1", "d.n >= 1")
    ):
        mutant = runner.run(suite())
    if mutant.wasSuccessful() or mutant.errors:
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
    expected = evaluate(raw, rows)
    for repetition in range(10):
        order = list(functions) if repetition % 2 else list(reversed(functions))
        for name in order:
            start = time.perf_counter_ns()
            actual = functions[name](raw, rows)
            samples[name].append(time.perf_counter_ns() - start)
            if actual != expected:
                raise RuntimeError("campaign_maximum_parity_failed")
    allocations = {}
    for name, function in functions.items():
        tracemalloc.start()
        function(raw, rows)
        _, allocations[name] = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    root = Path(__file__).parents[2]
    print(
        json.dumps(
            {
                "scope": "offline_campaign_aggregation_audit",
                "audit_policy_version": 2,
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
                "elapsed_ns": samples,
                "python_traced_peak_bytes": allocations,
                "measurement_limits": [
                    "Shared host, ten alternating-order repetitions; descriptive only.",
                    "Both paths share admission and declaration semantics; SQL aggregation is independent.",
                    "Tracing excludes preconstructed inputs and native SQLite allocations.",
                    "Whitespace-distinct bytes test input capacity, not independent physical evidence.",
                ],
                "source_sha256": {
                    name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                    for name in (
                        "aethron/_json_bounds.py",
                        "qualification/evidence.py",
                        "qualification/campaign.py",
                        "qualification/tests/test_evidence.py",
                        "qualification/tests/test_campaign.py",
                        "qualification/tests/test_campaign_audit.py",
                        "qualification/technology/campaign_sql.py",
                        "qualification/technology/compare_campaign.py",
                    )
                },
                "physical_qualification_passed": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
