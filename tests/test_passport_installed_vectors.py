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
    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_wrong_inbox_identity_prevents_success(self):
        for operation in ("put", "take"):
            original = getattr(RUNNER.BoundedInbox, operation)
            for field in ("peer", "expires_at_ms"):

                def changed(*args, original=original, field=field, **kwargs):
                    result = original(*args, **kwargs)
                    return SimpleNamespace(**(asdict(result) | {field: "wrong"}))

                with self.subTest(operation=operation, field=field):
                    with patch.object(RUNNER.BoundedInbox, operation, changed):
                        with self.assertRaises(AssertionError):
                            RUNNER.run(ROOT)

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_wrong_verification_metadata_prevents_success(self):
        for name, success, metadata in (
            ("verify", "authenticated", ("payload_sha256", "policy_revision", "expires_at")),
            ("verify_evidence", "bound", ("passport_sha256", "policy_revision", "expires_at")),
            ("validate_task", "validated", ("task_sha256", "expires_at", "evidence_verified")),
            (
                "verify_task_bundle",
                "bound",
                ("task_sha256", "passport_sha256", "policy_revision", "expires_at"),
            ),
            (
                "verify_federated_bundle",
                "bound",
                (
                    "task_sha256",
                    "passport_sha256",
                    "policy_revision",
                    "expires_at",
                    "federation_sha256",
                    "federation_revision",
                ),
            ),
        ):
            original = getattr(RUNNER, name)
            for status in (success, "rejected"):
                for field in metadata:

                    def changed(*args, original=original, status=status, field=field, **kwargs):
                        result = original(*args, **kwargs)
                        values = {item.name: getattr(result, item.name) for item in fields(result)}
                        for flag in ("motion_authority", "evidence_verified"):
                            values[flag] = getattr(result, flag)
                        if result.status == status:
                            values[field] = True if field == "evidence_verified" else "wrong"
                        return SimpleNamespace(**values)

                    with self.subTest(api=name, status=status, field=field):
                        with patch.object(RUNNER, name, changed):
                            with self.assertRaises(AssertionError):
                                RUNNER.run(ROOT)

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_wrong_signed_reference_prevents_success(self):
        for name in ("verify_evidence", "verify_task_bundle", "verify_federated_bundle"):
            original = getattr(RUNNER, name)
            for field in ("sha256", "kind"):

                def changed(*args, original=original, field=field, **kwargs):
                    result = original(*args, **kwargs)
                    if not result.evidence:
                        return result
                    references = list(result.evidence)
                    references[0] = SimpleNamespace(**(asdict(references[0]) | {field: "wrong"}))
                    values = {item.name: getattr(result, item.name) for item in fields(result)}
                    return SimpleNamespace(**(values | {"evidence": tuple(references)}))

                with self.subTest(api=name, field=field), patch.object(RUNNER, name, changed):
                    with self.assertRaises(AssertionError):
                        RUNNER.run(ROOT)

    def test_federation_floor_scenario_uses_real_api(self):
        from aethron.passport_floor_store import FederationFloorStore

        with patch.object(
            RUNNER, "FederationFloorStore", wraps=FederationFloorStore, create=True
        ) as store:
            RUNNER.check_federation_floor_persistence(ROOT)
            self.assertEqual(store.create.call_count, 1)
            self.assertGreaterEqual(store.call_count, 3)

    def test_federation_floor_write_loss_prevents_success(self):
        from aethron.passport_floor_store import FederationFloorStore

        def lost_time(store, *, now_s):
            return SimpleNamespace(**(asdict(store.read()) | {"minimum_time_s": now_s}))

        def lost_revision(store, federation, *, expected_federation_sha256, now_s):
            return SimpleNamespace(
                **(
                    asdict(store.read())
                    | {
                        "federation_revision": 6,
                        "minimum_time_s": now_s,
                        "federation_sha256": expected_federation_sha256,
                    }
                )
            )

        for method, replacement in (
            ("observe_time", lost_time),
            ("accept_federation", lost_revision),
        ):
            with (
                self.subTest(method=method),
                patch.object(FederationFloorStore, method, replacement),
            ):
                with self.assertRaises(AssertionError):
                    RUNNER.check_federation_floor_persistence(ROOT)

    def test_federation_floor_wrong_metadata_prevents_success(self):
        from aethron.passport_floor_store import FederationFloorStore

        read = FederationFloorStore.read
        for field, value in (
            ("local_domain", "other"),
            ("federation_revision", 99),
            ("minimum_time_s", 0),
            ("federation_sha256", "0" * 64),
            ("execution_authority", True),
            ("motion_authority", True),
            ("evidence_verified", True),
        ):

            def changed(store, field=field, value=value):
                return SimpleNamespace(**(asdict(read(store)) | {field: value}))

            with self.subTest(field=field), patch.object(FederationFloorStore, "read", changed):
                with self.assertRaises(AssertionError):
                    RUNNER.check_federation_floor_persistence(ROOT)

    def test_federation_floor_accepted_rollback_prevents_success(self):
        from aethron.passport_floor_store import FederationFloorStore, FloorStoreError

        for method in ("observe_time", "accept_federation"):
            original = getattr(FederationFloorStore, method)

            def changed(store, *args, original=original, **kwargs):
                try:
                    return original(store, *args, **kwargs)
                except FloorStoreError:
                    return store.read()

            with self.subTest(method=method), patch.object(FederationFloorStore, method, changed):
                with self.assertRaisesRegex(
                    AssertionError, "installed federation floor rollback accepted"
                ):
                    RUNNER.check_federation_floor_persistence(ROOT)

    def test_federation_admission_uses_real_api_without_crypto(self):
        from aethron.interop_federation import validate_pinned_federation

        with patch.object(
            RUNNER, "validate_pinned_federation", wraps=validate_pinned_federation, create=True
        ) as validator:
            RUNNER.check_federation_policy(ROOT)
            self.assertEqual(validator.call_count, 10)

    def test_federation_admission_wrong_metadata_prevents_success(self):
        from aethron.interop_federation import validate_pinned_federation

        for status in ("validated", "rejected"):
            for field, value in (
                ("federation_sha256", "e" * 64),
                ("federation_revision", 999),
                ("expires_at", 999),
                ("execution_authority", True),
                ("motion_authority", True),
                ("evidence_verified", True),
            ):

                def changed(*args, status=status, field=field, value=value, **kwargs):
                    result = validate_pinned_federation(*args, **kwargs)
                    values = asdict(result)
                    if result.status == status:
                        values[field] = value
                    return SimpleNamespace(**values)

                with self.subTest(status=status, field=field):
                    with patch.object(RUNNER, "validate_pinned_federation", changed, create=True):
                        with self.assertRaises(AssertionError):
                            RUNNER.check_federation_policy(ROOT)

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
        with patch.object(
            RUNNER, "check_federation_policy", wraps=RUNNER.check_federation_policy
        ) as admission:
            self.assertEqual(RUNNER.run(ROOT), 62)
            admission.assert_called_once_with(ROOT)
        with patch.object(
            RUNNER,
            "check_federation_floor_persistence",
            side_effect=AssertionError("missing federation persistence"),
        ):
            with self.assertRaisesRegex(AssertionError, "missing federation persistence"):
                RUNNER.run(ROOT)
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
            self.assertEqual(RUNNER.run(ROOT), 62)
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
