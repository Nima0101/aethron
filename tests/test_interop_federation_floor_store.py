"""Synthetic local-file federation floors; no hardware rollback qualification."""

import dataclasses
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from aethron import passport_floor_store as api
from aethron.interop_federation import verify_federated_bundle

ROOT = Path(__file__).resolve().parents[1]


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


class FederationFloorStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "federation ?#.sqlite")
        cases = json.loads(
            (ROOT / "examples/interop/federation-policy-vectors-v1.json").read_bytes()
        )["cases"]
        self.raw = cases[1]["federation"].encode()
        self.pin = hashlib.sha256(self.raw).hexdigest()
        self.arguments = cases[1]["arguments"]

    def create(self, **changes):
        return api.FederationFloorStore.create(
            self.path, **({"federation": self.raw, **self.arguments} | changes)
        )

    def reopen(self):
        return api.FederationFloorStore(self.path, local_domain="local-software")

    def accept(self, store, raw, now=1501):
        return store.accept_federation(
            raw, expected_federation_sha256=hashlib.sha256(raw).hexdigest(), now_s=now
        )

    def test_reopen_preserves_complete_immutable_metadata(self):
        self.create()
        row = self.reopen().read()
        self.assertEqual(
            dataclasses.asdict(row),
            {
                "local_domain": "local-software",
                "federation_revision": 5,
                "minimum_time_s": 1500,
                "federation_sha256": self.pin,
                "motion_authority": False,
                "execution_authority": False,
                "evidence_verified": False,
            },
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            row.minimum_time_s = 0

    def test_deny_all_commits_even_when_all_bundles_reject(self):
        store = self.create()
        doc = json.loads(self.raw)
        doc.update(revision=6, peers=[])
        raw = wire(doc)
        result = verify_federated_bundle(
            raw,
            b"",
            b"",
            b"",
            (),
            **(self.arguments | {"expected_federation_sha256": hashlib.sha256(raw).hexdigest()}),
            remote_domain="peer-software",
            expected_task_sha256="a" * 64,
            expected_subject_sha256="b" * 64,
            minimum_policy_revision=1,
        )
        self.assertEqual((result.status, result.reason), ("rejected", "untrusted_peer"))
        row = self.accept(store, raw)
        self.assertEqual((row.federation_revision, row.minimum_time_s), (6, 1501))
        self.assertEqual(row.federation_sha256, hashlib.sha256(raw).hexdigest())
        with self.assertRaisesRegex(api.FloorStoreError, "^federation_rejected$"):
            self.accept(self.reopen(), self.raw, 1502)
        self.assertEqual(self.reopen().read(), row)

    def test_same_revision_equivocation_rejects_but_identical_bytes_advance_time(self):
        store = self.create()
        changed = json.loads(self.raw)
        changed["peers"] = []
        with self.assertRaisesRegex(api.FloorStoreError, "^federation_equivocation$"):
            self.accept(store, wire(changed))
        self.assertEqual(self.reopen().read().minimum_time_s, 1500)
        self.assertEqual(self.accept(store, self.raw).minimum_time_s, 1501)

    def test_time_survives_expiry_and_rejects_older_observation(self):
        store = self.create()
        store.observe_time(now_s=1600)
        with self.assertRaisesRegex(api.FloorStoreError, "^federation_rejected$"):
            self.accept(store, self.raw, 1600)
        with self.assertRaisesRegex(api.FloorStoreError, "^time_rollback$"):
            store.observe_time(now_s=1599)
        self.assertEqual(self.reopen().read().minimum_time_s, 1600)
        self.assertEqual(store.observe_time(now_s=1600).minimum_time_s, 1600)

    def test_missing_and_invalid_bootstrap_never_create_and_existing_never_overwrites(self):
        with self.assertRaises(api.FloorStoreError):
            self.reopen()
        self.assertFalse(Path(self.path).exists())
        with self.assertRaisesRegex(api.FloorStoreError, "^federation_rejected$"):
            self.create(expected_federation_sha256="0" * 64)
        self.assertFalse(Path(self.path).exists())
        self.create()
        before = Path(self.path).read_bytes()
        with self.assertRaises(api.FloorStoreError):
            self.create()
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_invalid_admission_and_domain_do_not_advance_any_floor(self):
        store = self.create()
        before = store.read()
        for raw in (b"{}", self.raw + b"\n", bytearray(self.raw)):
            with self.subTest(raw=type(raw)), self.assertRaises(api.FloorStoreError):
                self.accept(store, raw)
        changed = json.loads(self.raw)
        changed.update(revision=6, local_domain="other")
        with self.assertRaises(api.FloorStoreError):
            self.accept(store, wire(changed))
        for time in (True, 1.5, -1, 2**53, None, 1499):
            with self.subTest(time=time), self.assertRaises(api.FloorStoreError):
                store.observe_time(now_s=time)
        self.assertEqual(self.reopen().read(), before)

    def test_profiles_are_disjoint_and_wrong_domain_rejects(self):
        self.create()
        with self.assertRaises(api.FloorStoreError):
            api.PolicyFloorStore(self.path, scope="local-software")
        with self.assertRaises(api.FloorStoreError):
            api.FederationFloorStore(self.path, local_domain="other")
        Path(self.path).unlink()
        case = json.loads((ROOT / "examples/passports/vectors.json").read_bytes())["cases"][0]
        raw = case["policy"].encode()
        api.PolicyFloorStore.create(
            self.path,
            scope="local-software",
            policy=raw,
            expected_policy_sha256=hashlib.sha256(raw).hexdigest(),
            now_s=1500,
            minimum_time_s=1400,
            minimum_policy_revision=3,
        )
        with self.assertRaises(api.FloorStoreError):
            self.reopen()

    def test_contention_and_other_handle_update_do_not_lose_floors(self):
        store = self.create()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(api.FloorStoreError, "^store_unavailable$"):
                store.observe_time(now_s=1502)
            db.execute("ROLLBACK")
        self.assertEqual(store.read().minimum_time_s, 1500)
        self.reopen().observe_time(now_s=1503)
        with self.assertRaises(api.FloorStoreError):
            self.accept(store, self.raw, 1502)
        self.assertEqual(store.read().minimum_time_s, 1503)

    def test_other_process_update_is_seen_by_existing_handle(self):
        store = self.create()
        code = (
            "import sys; from aethron.passport_floor_store import FederationFloorStore; "
            "print(FederationFloorStore(sys.argv[1], local_domain='local-software')"
            ".observe_time(now_s=1505).minimum_time_s)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, self.path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "1505")
        self.assertEqual(store.read().minimum_time_s, 1505)

    def test_commit_failure_rolls_back_revision_digest_and_time(self):
        store = self.create()
        before = store.read()
        changed = json.loads(self.raw)
        changed.update(revision=6, peers=[])
        connect = sqlite3.connect

        class FailCommit(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("injected failure")
                return super().execute(sql, parameters)

        def failing(*args, **kwargs):
            return connect(*args, **kwargs, factory=FailCommit)

        with patch.object(api.sqlite3, "connect", failing):
            with self.assertRaisesRegex(api.FloorStoreError, "^store_unavailable$"):
                self.accept(store, wire(changed))
        self.assertEqual(self.reopen().read(), before)

    def test_changed_schema_row_and_format_are_rejected(self):
        self.create()
        original = Path(self.path).read_bytes()
        for sql in (
            "UPDATE federation_floor SET revision=0",
            "UPDATE federation_floor SET time_s=-1",
            "UPDATE federation_floor SET federation_sha256='bad'",
            "UPDATE federation_floor SET local_domain='other'",
            "DELETE FROM federation_floor",
            "PRAGMA application_id=1096042033",
            "PRAGMA user_version=2",
            "CREATE TABLE unexpected (value TEXT)",
        ):
            Path(self.path).write_bytes(original)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute(sql)
            with self.subTest(sql=sql), self.assertRaises(api.FloorStoreError):
                self.reopen()

    def test_whole_file_restore_remains_an_explicit_limit(self):
        store = self.create()
        backup = Path(self.path).read_bytes()
        store.observe_time(now_s=1800)
        Path(self.path).write_bytes(backup)
        self.assertEqual(self.reopen().read().minimum_time_s, 1500)
