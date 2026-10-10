"""Negative controls for the fixed installed-package behavioral corpus."""

import importlib.util
import json
import tempfile
import unittest
from dataclasses import asdict, fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "passport_installed_vectors", ROOT / "scripts/passport_installed_vectors.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None


class InstalledVectorTests(unittest.TestCase):
    def test_floor_persistence_is_executed_with_real_api(self):
        from aethron.passport_floor_store import PolicyFloorStore

        with patch.object(RUNNER, "PolicyFloorStore", wraps=PolicyFloorStore, create=True) as store:
            RUNNER.check_floor_persistence(ROOT)
            self.assertEqual(store.create.call_count, 1)
            self.assertGreaterEqual(store.call_count, 3)

    def test_floor_write_loss_prevents_success(self):
        from aethron.passport_floor_store import PolicyFloorStore

        def lost_write(store, *, now_s):
            return SimpleNamespace(**(asdict(store.read()) | {"minimum_time_s": now_s}))

        with patch.object(PolicyFloorStore, "observe_time", lost_write):
            with self.assertRaises(AssertionError):
                RUNNER.check_floor_persistence(ROOT)

    def test_floor_policy_write_loss_prevents_success(self):
        from hashlib import sha256

        from aethron.passport_floor_store import PolicyFloorStore

        def lost_write(store, policy, *, expected_policy_sha256, now_s):
            return SimpleNamespace(
                **(
                    asdict(store.read())
                    | {
                        "policy_revision": json.loads(policy)["revision"],
                        "policy_sha256": sha256(policy).hexdigest(),
                        "minimum_time_s": now_s,
                    }
                )
            )

        with patch.object(PolicyFloorStore, "accept_policy", lost_write):
            with self.assertRaises(AssertionError):
                RUNNER.check_floor_persistence(ROOT)

    def test_floor_rollback_acceptance_prevents_success(self):
        from aethron.passport_floor_store import FloorStoreError, PolicyFloorStore

        for name in ("observe_time", "accept_policy"):
            original = getattr(PolicyFloorStore, name)

            def suppress_rejection(store, *args, method=original, **kwargs):
                try:
                    return method(store, *args, **kwargs)
                except FloorStoreError:
                    return store.read()

            with self.subTest(method=name):
                with patch.object(PolicyFloorStore, name, suppress_rejection):
                    with self.assertRaisesRegex(
                        AssertionError, "installed floor rollback accepted"
                    ):
                        RUNNER.check_floor_persistence(ROOT)

    def test_wrong_floor_metadata_prevents_success(self):
        from aethron.passport_floor_store import PolicyFloorStore

        original = PolicyFloorStore.read
        for field, value in (
            ("scope", "wrong"),
            ("policy_revision", 99),
            ("minimum_time_s", 0),
            ("policy_sha256", "0" * 64),
            ("execution_authority", True),
            ("motion_authority", True),
            ("evidence_verified", True),
        ):

            def changed(*args, changed_field=field, changed_value=value, **kwargs):
                result = original(*args, **kwargs)
                return SimpleNamespace(**(asdict(result) | {changed_field: changed_value}))

            with self.subTest(field=field):
                with patch.object(PolicyFloorStore, "read", changed):
                    with self.assertRaises(AssertionError):
                        RUNNER.check_floor_persistence(ROOT)

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_wrong_inbox_result_flags_prevent_success(self):
        for operation in ("put", "take"):
            original = getattr(RUNNER.BoundedInbox, operation)
            for field in ("execution_authority", "evidence_verified"):

                def changed(*args, method=original, changed_field=field, **kwargs):
                    result = method(*args, **kwargs)
                    values = {item.name: getattr(result, item.name) for item in fields(result)}
                    return SimpleNamespace(**(values | {changed_field: True}))

                with self.subTest(operation=operation, field=field):
                    with patch.object(RUNNER.BoundedInbox, operation, changed):
                        with self.assertRaises(AssertionError):
                            RUNNER.run(ROOT)

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_wrong_bundle_evidence_flag_prevents_success(self):
        original = RUNNER.verify_task_bundle

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            values = {item.name: getattr(result, item.name) for item in fields(result)}
            return SimpleNamespace(**(values | {"evidence_verified": True}))

        with patch.object(RUNNER, "verify_task_bundle", changed):
            with self.assertRaises(AssertionError):
                RUNNER.run(ROOT)

    def test_optimized_mode_rejects_before_fixture_reads(self):
        for mode in (1, 2):
            with self.subTest(mode=mode):
                with patch.object(
                    RUNNER, "sys", SimpleNamespace(flags=SimpleNamespace(optimize=mode))
                ):
                    with self.assertRaisesRegex(RuntimeError, "optimized_execution_not_supported"):
                        RUNNER.run(Path("missing-fixture-root"))

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_current_corpora_execute_all_checks(self):
        self.assertEqual(RUNNER.run(ROOT), 51)
        from aethron.passport_floor_store import FloorStoreError

        # A failed floor scenario must prevent the complete runner reporting success.
        with patch.object(
            RUNNER.PolicyFloorStore, "create", side_effect=FloorStoreError("store_unavailable")
        ):
            with self.assertRaisesRegex(FloorStoreError, "^store_unavailable$"):
                RUNNER.run(ROOT)

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_policy_corpus_is_executed_with_real_api(self):
        from aethron.passports import validate_pinned_policy

        relative = "examples/passports/policy-vectors-v1.json"
        self.assertIn(relative, RUNNER.CORPORA)
        with patch.object(
            RUNNER, "validate_pinned_policy", wraps=validate_pinned_policy, create=True
        ) as validator:
            self.assertEqual(RUNNER.run(ROOT), 51)
            self.assertEqual(validator.call_count, 10)

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_wrong_policy_result_fields_prevent_success(self):
        from aethron.passports import validate_pinned_policy

        # Inject one incorrect boundary result while executing the real runner.
        for field, value in (
            ("status", "wrong"),
            ("reason", "wrong"),
            ("policy_sha256", "0" * 64),
            ("policy_revision", 99),
            ("expires_at", 9999),
            ("execution_authority", True),
            ("motion_authority", True),
            ("evidence_verified", True),
        ):

            def changed(*args, changed_field=field, changed_value=value, **kwargs):
                result = validate_pinned_policy(*args, **kwargs)
                return SimpleNamespace(**(asdict(result) | {changed_field: changed_value}))

            with self.subTest(field=field):
                with patch.object(RUNNER, "validate_pinned_policy", changed, create=True):
                    with self.assertRaises(AssertionError):
                        RUNNER.run(ROOT)

    def test_missing_or_changed_cases_reject_for_every_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in RUNNER.CORPORA:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                original = (ROOT / relative).read_bytes()
                for mode in ("empty", "truncated", "duplicate", "changed-outcome"):
                    data = json.loads(original)
                    if mode == "empty":
                        data["cases"] = []
                    elif mode == "truncated":
                        data["cases"].pop()
                    elif mode == "duplicate":
                        data["cases"][-1] = data["cases"][0]
                    else:
                        data["cases"][0]["status"] = "unreviewed"
                    path.write_text(json.dumps(data))
                    with self.subTest(path=relative, mode=mode):
                        with self.assertRaisesRegex(ValueError, "invalid_vector_coverage"):
                            RUNNER.load_vectors(root, relative)

    def test_missing_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                RUNNER.load_vectors(Path(directory), next(iter(RUNNER.CORPORA)))

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_behavior_mismatch_still_fails_with_intact_corpora(self):
        from aethron.passports import VerificationResult

        with patch.object(
            RUNNER, "verify", return_value=VerificationResult("authenticated", "wrong")
        ):
            with self.assertRaises(AssertionError):
                RUNNER.run(ROOT)


if __name__ == "__main__":
    unittest.main()
