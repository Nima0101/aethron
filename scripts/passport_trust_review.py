"""Bounded defensive mutation evidence for the P16 trust review; no deployment claim."""

import hashlib
import io
import json
import platform
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests import test_passports  # noqa: E402

MUTATIONS = (
    (
        "unselected_metadata",
        'for key in value["keys"]:',
        'for key in value["keys"][:1]:',
        "test_unselected_key_metadata_is_not_ignored",
    ),
    (
        "effective_expiry",
        'min(statement["expires_at"], trust["expires_at"]),',
        'statement["expires_at"],',
        "test_policy_expiry_caps_result_and_requires_reverification",
    ),
    (
        "evidence_revocation",
        'or any(e["sha256"] in trust["revoked_evidence"] for e in statement["evidence"])',
        "or False",
        "test_revocation_is_rechecked_after_success",
    ),
    (
        "rejection_metadata",
        'return VerificationResult("rejected", reason)',
        'return VerificationResult("rejected", reason, policy_revision=1)',
        "test_unsupported_crypto_rejects_without_authentication_metadata",
    ),
)


def _run(source, methods):
    # Contexts restore the imported test verifier and module table on every exit.
    module = types.ModuleType("aethron._passport_review_mutant")
    module.__package__ = "aethron"
    with patch.dict(sys.modules, {module.__name__: module}):
        exec(compile(source, "<passport-review-mutant>", "exec"), module.__dict__)
        with patch.object(test_passports, "passports", module):
            suite = unittest.TestSuite(
                test_passports.PassportVerificationTests(method) for method in methods
            )
            return unittest.TextTestRunner(stream=io.StringIO()).run(suite)


def main():
    if sys.flags.optimize:
        raise RuntimeError("optimized_probe_execution_forbidden")
    paths = (
        "aethron/passports.py",
        "aethron/_json_bounds.py",
        "tests/test_passports.py",
        "scripts/passport_trust_review.py",
        "examples/passports/vectors.json",
    )
    sources = {path: (ROOT / path).read_bytes() for path in paths}
    source = sources["aethron/passports.py"].decode("utf-8")
    baseline = _run(source, [method for _, _, _, method in MUTATIONS])
    if (
        not baseline.wasSuccessful()
        or baseline.skipped
        or baseline.expectedFailures
        or baseline.testsRun != len(MUTATIONS)
    ):
        raise RuntimeError("mutation_baseline_failed")
    results = []
    for name, old, new, method in MUTATIONS:
        assert source.count(old) == 1, "mutation no longer maps uniquely to source"
        # Alter an isolated module in memory; production files are never rewritten.
        result = _run(source.replace(old, new), [method])
        assert result.failures and not result.errors and not result.skipped, name
        results.append({"guard": name, "expected_assertion_failures": len(result.failures)})
    if any((ROOT / path).read_bytes() != raw for path, raw in sources.items()):
        raise RuntimeError("mutation_source_changed")
    print(
        json.dumps(
            {
                "review_order_version": 3,
                "python": platform.python_version(),
                "baseline_tests": baseline.testsRun,
                "source_sha256": {p: hashlib.sha256(raw).hexdigest() for p, raw in sources.items()},
                "source_scope": "Listed project files matched before/after execution; mutants compiled from captured passport source. Not an atomic snapshot, loaded-code attestation or dependency closure; transient changes restored between reads are not detected.",
                "mutations": results,
                "limit": "In-memory guard-removal tests; not a cryptographic validation or hardware qualification.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
