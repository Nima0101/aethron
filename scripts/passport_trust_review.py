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


def main():
    source = (ROOT / "aethron/passports.py").read_text()
    results = []
    for name, old, new, method in MUTATIONS:
        assert source.count(old) == 1, "mutation no longer maps uniquely to source"
        # Alter an isolated module in memory; production files are never rewritten.
        mutant = types.ModuleType("aethron._passport_review_mutant")
        mutant.__package__ = "aethron"
        with patch.dict(sys.modules, {mutant.__name__: mutant}):
            exec(
                compile(source.replace(old, new), "<passport-review-mutant>", "exec"),
                mutant.__dict__,
            )
            with patch.object(test_passports, "passports", mutant):
                suite = unittest.TestSuite([test_passports.PassportVerificationTests(method)])
                result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        assert result.failures and not result.errors and not result.skipped, name
        results.append({"guard": name, "expected_assertion_failures": len(result.failures)})
    paths = ("aethron/passports.py", "tests/test_passports.py", "scripts/passport_trust_review.py")
    print(
        json.dumps(
            {
                "review_order_version": 3,
                "python": platform.python_version(),
                "source_sha256": {
                    p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths
                },
                "mutations": results,
                "limit": "In-memory guard-removal tests; not a cryptographic validation or hardware qualification.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
