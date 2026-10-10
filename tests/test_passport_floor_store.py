"""Local files only; synthetic policies and no device/security accreditation."""

import dataclasses
import hashlib
import importlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

from aethron.passports import verify

ROOT = Path(__file__).resolve().parents[1]


class PolicyFloorStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron.passport_floor_store"), "floor store API missing"
        )
        self.api = importlib.import_module("aethron.passport_floor_store")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "scope ?#.sqlite")
        self.case = json.loads((ROOT / "examples/passports/vectors.json").read_bytes())["cases"][0]
        self.raw = self.case["policy"].encode()
        self.pin = hashlib.sha256(self.raw).hexdigest()

    def create(self, **changes):
        args = {
            "scope": "local",
            "policy": self.raw,
            "expected_policy_sha256": self.pin,
            "now_s": 1500,
            "minimum_time_s": 1400,
            "minimum_policy_revision": 3,
        }
        return self.api.PolicyFloorStore.create(self.path, **(args | changes))

    def reopen(self):
        return self.api.PolicyFloorStore(self.path, scope="local")

    @contextmanager
    def fail_close(self, error_type):
        connect = sqlite3.connect

        class FailClose(sqlite3.Connection):
            def close(self):
                super().close()  # Real teardown; inject only the reported failure.
                raise error_type("synthetic storage diagnostic")

        def failing(*args, **kwargs):
            return connect(*args, **kwargs, factory=FailClose)

        with patch.object(self.api.sqlite3, "connect", failing):
            yield

    def assert_storage_failure(self, operation):
        try:
            operation()
        except Exception as error:
            self.assertIs(type(error), self.api.FloorStoreError)
            self.assertEqual(str(error), "store_unavailable")
            self.assertTrue(error.__suppress_context__)
        else:
            self.fail("cleanup failure returned success")

    def test_close_failure_after_commit_is_fixed_and_does_not_imply_rollback(self):
        store = self.create()
        for error_type in (sqlite3.OperationalError, OSError):
            with self.subTest(error=error_type.__name__):
                with self.fail_close(error_type):
                    self.assert_storage_failure(lambda: store.observe_time(now_s=1800))
                # The commit precedes cleanup; an error is not proof of non-commit.
                self.assertEqual(self.reopen().read().minimum_time_s, 1800)
                with self.fail_close(error_type):
                    self.assert_storage_failure(store.read)

    def test_close_failure_after_rejection_preserves_existing_floor(self):
        store = self.create()
        before = store.read()
        for error_type in (sqlite3.OperationalError, OSError):
            with self.subTest(error=error_type.__name__):
                with self.fail_close(error_type):
                    self.assert_storage_failure(lambda: store.observe_time(now_s=1499))
                self.assertEqual(self.reopen().read(), before)

    def test_close_failure_during_create_does_not_reset_committed_store(self):
        with self.fail_close(sqlite3.OperationalError):
            self.assert_storage_failure(self.create)
        self.assertEqual(self.reopen().read().minimum_time_s, 1500)
        with self.assertRaises(self.api.FloorStoreError):
            self.create()

    def test_original_v1_disk_format_remains_readable_and_writable(self):
        # Literal original schema/markers: independent of the implementation constants.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "CREATE TABLE policy_floor (id INTEGER PRIMARY KEY CHECK(id=1), "
                "scope TEXT NOT NULL, revision INTEGER NOT NULL, time_s INTEGER NOT NULL, "
                "policy_sha256 TEXT NOT NULL)"
            )
            db.execute("PRAGMA application_id=1096042033")
            db.execute("PRAGMA user_version=1")
            db.execute("INSERT INTO policy_floor VALUES (1, 'local', 3, 1500, ?)", (self.pin,))
        store = self.reopen()
        self.assertEqual(store.read().policy_sha256, self.pin)
        store.observe_time(now_s=1501)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT * FROM policy_floor").fetchall(),
                [(1, "local", 3, 1501, self.pin)],
            )
            self.assertEqual(db.execute("PRAGMA application_id").fetchone(), (1096042033,))
            self.assertEqual(db.execute("PRAGMA user_version").fetchone(), (1,))

    def test_reopen_keeps_complete_metadata_without_authority(self):
        self.create()
        row = self.reopen().read()
        self.assertEqual((row.scope, row.policy_revision, row.minimum_time_s), ("local", 3, 1500))
        self.assertEqual(row.policy_sha256, self.pin)
        for field in ("motion_authority", "execution_authority", "evidence_verified"):
            self.assertIs(dataclasses.asdict(row)[field], False)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            row.minimum_time_s = 0

    def test_open_never_creates_and_create_never_overwrites(self):
        with self.assertRaises(self.api.FloorStoreError):
            self.reopen()
        self.assertFalse(Path(self.path).exists())
        self.create()
        before = Path(self.path).read_bytes()
        with self.assertRaises(self.api.FloorStoreError):
            self.create()
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_revoking_policy_persists_independent_of_passport_success(self):
        store = self.create()
        policy = json.loads(self.raw)
        policy["revision"] = 4
        policy["revoked_keys"] = [policy["keys"][0]["key_id"]]
        raw = json.dumps(policy).encode()
        pin = hashlib.sha256(raw).hexdigest()
        row = store.accept_policy(raw, expected_policy_sha256=pin, now_s=1501)
        self.assertEqual(
            (row.policy_revision, row.minimum_time_s, row.policy_sha256), (4, 1501, pin)
        )
        result = verify(self.case["envelope"].encode(), raw, **self.case["arguments"])
        self.assertEqual((result.status, result.reason), ("rejected", "revoked"))
        with self.assertRaises(self.api.FloorStoreError):
            self.reopen().accept_policy(self.raw, expected_policy_sha256=self.pin, now_s=1502)
        self.assertEqual(self.reopen().read(), row)

    def test_same_revision_different_exact_pin_rejects_without_advancing_time(self):
        store = self.create()
        raw = json.dumps(json.loads(self.raw), indent=2).encode()
        self.assertNotEqual(raw, self.raw)
        with self.assertRaisesRegex(self.api.FloorStoreError, "^policy_equivocation$"):
            store.accept_policy(
                raw, expected_policy_sha256=hashlib.sha256(raw).hexdigest(), now_s=1501
            )
        self.assertEqual(store.read().minimum_time_s, 1500)
        self.assertEqual(
            store.accept_policy(
                self.raw, expected_policy_sha256=self.pin, now_s=1501
            ).minimum_time_s,
            1501,
        )

    def test_time_observation_survives_expired_policy_rejection(self):
        store = self.create()
        store.observe_time(now_s=2200)
        with self.assertRaises(self.api.FloorStoreError):
            store.accept_policy(self.raw, expected_policy_sha256=self.pin, now_s=2200)
        self.assertEqual(self.reopen().read().minimum_time_s, 2200)
        with self.assertRaises(self.api.FloorStoreError):
            store.observe_time(now_s=2199)
        self.assertEqual(store.observe_time(now_s=2200).minimum_time_s, 2200)

    def test_invalid_input_does_not_change_persisted_snapshot(self):
        store = self.create()
        before = store.read()
        for value in (True, 1500.0, -1, 2**53, "1500"):
            with self.subTest(value=value), self.assertRaises(self.api.FloorStoreError):
                store.observe_time(now_s=value)
        for raw, pin in ((b"{}", self.pin), (self.raw, "0" * 64), (bytearray(self.raw), self.pin)):
            with self.subTest(raw_type=type(raw)), self.assertRaises(self.api.FloorStoreError):
                store.accept_policy(raw, expected_policy_sha256=pin, now_s=1501)
        self.assertEqual(self.reopen().read(), before)

    def test_invalid_bootstrap_leaves_no_new_file(self):
        with self.assertRaises(self.api.FloorStoreError):
            self.create(expected_policy_sha256="0" * 64)
        self.assertFalse(Path(self.path).exists())

    def test_wrong_scope_and_changed_schema_fail_closed(self):
        self.create()
        with self.assertRaises(self.api.FloorStoreError):
            self.api.PolicyFloorStore(self.path, scope="other")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE unexpected (value TEXT)")
        with self.assertRaises(self.api.FloorStoreError):
            self.reopen()

    def test_missing_corrupt_and_oversize_stores_are_not_reset(self):
        for raw in (b"", b"broken sqlite", b"x" * 65537):
            Path(self.path).write_bytes(raw)
            with self.subTest(size=len(raw)), self.assertRaises(self.api.FloorStoreError):
                self.reopen()
            self.assertEqual(Path(self.path).read_bytes(), raw)

    def test_page_limit_cannot_silently_exceed_requested_bound(self):
        self.create()
        # A valid metadata row/schema can retain free pages after maintenance.
        # Small pages keep this fixture under the independent 65536-byte limit.
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute("PRAGMA page_size=512")
            db.execute("VACUUM")
            db.execute("CREATE TABLE scratch (value BLOB)")
            db.execute("INSERT INTO scratch VALUES (zeroblob(20000))")
            db.execute("DROP TABLE scratch")
            self.assertGreater(db.execute("PRAGMA page_count").fetchone()[0], 16)
        before = Path(self.path).read_bytes()
        self.assertLessEqual(len(before), 65536)
        with self.assertRaisesRegex(self.api.FloorStoreError, "^invalid_store$"):
            self.reopen()
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_competing_writer_fails_without_losing_committed_floor(self):
        store = self.create()
        db = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(db.close)
        db.execute("BEGIN IMMEDIATE")
        with self.assertRaisesRegex(self.api.FloorStoreError, "^store_unavailable$"):
            store.observe_time(now_s=1700)
        db.execute("ROLLBACK")
        self.assertEqual(store.read().minimum_time_s, 1500)
        other = self.reopen()
        other.observe_time(now_s=1800)
        with self.assertRaises(self.api.FloorStoreError):
            store.observe_time(now_s=1700)
        self.assertEqual(store.read().minimum_time_s, 1800)

    def test_other_process_update_is_seen_by_existing_handle(self):
        store = self.create()
        code = (
            "import sys; from aethron.passport_floor_store import PolicyFloorStore; "
            "print(PolicyFloorStore(sys.argv[1], scope='local').observe_time(now_s=1800).minimum_time_s)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, self.path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "1800")
        self.assertEqual(store.read().minimum_time_s, 1800)

    def test_commit_failure_rolls_back_real_update(self):
        store = self.create()
        connect = sqlite3.connect

        class FailCommit(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("injected commit failure")
                return super().execute(sql, parameters)

        def failing(*args, **kwargs):
            return connect(*args, **kwargs, factory=FailCommit)

        with patch.object(self.api.sqlite3, "connect", failing):
            with self.assertRaisesRegex(self.api.FloorStoreError, "^store_unavailable$"):
                store.observe_time(now_s=1800)
        self.assertEqual(self.reopen().read().minimum_time_s, 1500)

    def test_changed_row_metadata_and_format_version_are_rejected(self):
        self.create()
        original = Path(self.path).read_bytes()
        statements = (
            "UPDATE policy_floor SET revision=0",
            "UPDATE policy_floor SET time_s=-1",
            "UPDATE policy_floor SET policy_sha256='bad'",
            "DELETE FROM policy_floor",
            "PRAGMA user_version=2",
            "PRAGMA application_id=0",
        )
        for sql in statements:
            Path(self.path).write_bytes(original)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute(sql)
            with self.subTest(sql=sql), self.assertRaises(self.api.FloorStoreError):
                self.reopen()

    def test_untrusted_configuration_cannot_select_memory_or_relative_store(self):
        for path in (":memory:", "relative.sqlite", "file:state?mode=memory", "", None, "/\ud800"):
            with self.subTest(path=path), self.assertRaises(self.api.FloorStoreError):
                self.api.PolicyFloorStore(path, scope="local")
        with self.assertRaises(self.api.FloorStoreError):
            self.create(scope="not a scope")
        self.assertFalse(Path(self.path).exists())

    def test_whole_file_restore_is_not_hardware_rollback_detection(self):
        store = self.create()
        backup = Path(self.path).read_bytes()
        store.observe_time(now_s=1800)
        Path(self.path).write_bytes(backup)
        # Known negative evidence: external storage rollback is outside this API.
        self.assertEqual(self.reopen().read().minimum_time_s, 1500)


if __name__ == "__main__":
    unittest.main()
