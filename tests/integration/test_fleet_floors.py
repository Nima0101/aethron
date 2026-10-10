"""One committed floor pair survives reopen and fails closed on storage faults."""

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.runtime.fleet_floors import FleetFloorStore


class FleetFloorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "floors.db"

    def initialize(self):
        return FleetFloorStore.initialize(self.path, minimum_version=3, minimum_time_s=1000)

    def test_invalid_path_arguments_use_fixed_errors(self):
        for value in (None, [], 3, b"private"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
                    FleetFloorStore(value)

    def test_invalid_initial_floors_do_not_create_a_database(self):
        for version, time in ((True, 0), (0, 0), (1, True), (1, -1), (1.0, 0)):
            with self.subTest(version=version, time=time):
                with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
                    FleetFloorStore.initialize(
                        self.path, minimum_version=version, minimum_time_s=time
                    )
                self.assertFalse(self.path.exists())

    def test_invalid_persisted_floor_cannot_be_read_or_advanced(self):
        store = self.initialize()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("UPDATE fleet_floor SET minimum_version=-1")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            store.read()
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            store.advance(minimum_version=4, minimum_time_s=2000)

    def test_commits_require_delete_journal_and_extra_synchronization(self):
        connect = sqlite3.connect
        observed = []

        class InspectCommit(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    observed.append(
                        (
                            super().execute("PRAGMA journal_mode").fetchone()[0],
                            super().execute("PRAGMA synchronous").fetchone()[0],
                        )
                    )
                return super().execute(sql, parameters)

        with patch(
            "aethron_edge.runtime.fleet_floors.sqlite3.connect",
            side_effect=lambda *a, **kw: connect(*a, **kw, factory=InspectCommit),
        ):
            store = self.initialize()
            store.advance(minimum_version=4, minimum_time_s=2000)
        self.assertEqual(observed, [("delete", 3), ("delete", 3)])

    def test_unavailable_durability_settings_reject_before_floor_changes(self):
        store = self.initialize()
        connect = sqlite3.connect
        for ignored in ("synchronous", "journal_mode"):

            class WeakenSettings(sqlite3.Connection):
                def execute(self, sql, parameters=(), *, setting=ignored):
                    if sql.startswith(f"PRAGMA {setting}="):
                        sql = f"PRAGMA {setting}=" + (
                            "OFF" if setting == "synchronous" else "MEMORY"
                        )
                    return super().execute(sql, parameters)

            with self.subTest(ignored=ignored):
                with patch(
                    "aethron_edge.runtime.fleet_floors.sqlite3.connect",
                    side_effect=lambda *a, **kw: connect(*a, **kw, factory=WeakenSettings),
                ):
                    with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
                        store.advance(minimum_version=4, minimum_time_s=2000)
                self.assertEqual(
                    (store.read().minimum_version, store.read().minimum_time_s), (3, 1000)
                )

    def test_abrupt_process_exit_preserves_only_committed_pair(self):
        store = self.initialize()
        program = """
import os, sys
from pathlib import Path
from aethron_edge.runtime.fleet_floors import FleetFloorStore
store = FleetFloorStore(Path(sys.argv[1]))
if sys.argv[2] == 'before_commit':
    with store.guarded_advance(minimum_version=5, minimum_time_s=2000):
        os._exit(73)
else:
    store.advance(minimum_version=5, minimum_time_s=2000)
    os._exit(74)
"""
        for phase, code, expected in (
            ("before_commit", 73, (3, 1000)),
            ("after_commit", 74, (5, 2000)),
        ):
            with self.subTest(phase=phase):
                child = subprocess.run(
                    [sys.executable, "-c", program, str(self.path), phase],
                    timeout=10,
                    check=False,
                    capture_output=True,
                )
                self.assertEqual(child.returncode, code, child.stderr.decode())
                floor = store.read()
                self.assertEqual((floor.minimum_version, floor.minimum_time_s), expected)

    def test_reopen_preserves_both_committed_floors(self):
        store = self.initialize()
        store.advance(minimum_version=5, minimum_time_s=2000)
        result = FleetFloorStore(self.path).read()
        self.assertEqual((result.minimum_version, result.minimum_time_s), (5, 2000))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_existing_file_cannot_be_reinitialized(self):
        store = self.initialize()
        store.advance(minimum_version=6, minimum_time_s=3000)
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            self.initialize()
        result = store.read()
        self.assertEqual((result.minimum_version, result.minimum_time_s), (6, 3000))

    def test_regression_of_either_value_rejects_the_whole_pair(self):
        store = self.initialize()
        for version, time in ((2, 2000), (4, 999)):
            with self.subTest(version=version, time=time):
                with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
                    store.advance(minimum_version=version, minimum_time_s=time)
                result = store.read()
                self.assertEqual((result.minimum_version, result.minimum_time_s), (3, 1000))
        self.assertEqual(store.advance(minimum_version=3, minimum_time_s=1000), store.read())

    def test_stale_instance_cannot_overwrite_another_writers_floor(self):
        first = self.initialize()
        second = FleetFloorStore(self.path)
        first.read()
        second.advance(minimum_version=5, minimum_time_s=2000)
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            first.advance(minimum_version=4, minimum_time_s=3000)
        self.assertEqual(first.read().minimum_version, 5)
        self.assertEqual(first.read().minimum_time_s, 2000)

    def test_failed_commit_cannot_publish_or_persist_a_partial_advance(self):
        store = self.initialize()
        connect = sqlite3.connect

        class FailedCommit(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("injected storage failure")
                return super().execute(sql, parameters)

        def fail_commit(*args, **kwargs):
            return connect(*args, **kwargs, factory=FailedCommit)

        with patch("aethron_edge.runtime.fleet_floors.sqlite3.connect", fail_commit):
            with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
                store.advance(minimum_version=8, minimum_time_s=9000)
        result = FleetFloorStore(self.path).read()
        self.assertEqual((result.minimum_version, result.minimum_time_s), (3, 1000))

    def test_competing_write_lock_fails_closed(self):
        store = self.initialize()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
                store.advance(minimum_version=4, minimum_time_s=2000)
        finally:
            connection.close()
        self.assertEqual(store.read().minimum_version, 3)

    def test_missing_or_deleted_database_never_reinitializes(self):
        store = FleetFloorStore(self.path)
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            store.read()
        self.assertFalse(self.path.exists())
        self.initialize()
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            store.advance(minimum_version=4, minimum_time_s=2000)
        self.assertFalse(self.path.exists())

    def test_corruption_and_oversize_fail_without_replacement(self):
        self.path.write_bytes(b"private invalid database")
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            FleetFloorStore(self.path).read()
        self.assertEqual(self.path.read_bytes(), b"private invalid database")
        with self.path.open("wb") as stream:
            stream.truncate(1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            FleetFloorStore(self.path).read()

    def test_links_and_special_files_cannot_be_opened_as_a_store(self):
        store = self.initialize()
        target = self.path.with_suffix(".original")
        self.path.rename(target)
        self.path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            store.read()
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
            store.read()

    def test_unexpected_schema_or_missing_row_cannot_supply_defaults(self):
        store = self.initialize()
        for sql in ("CREATE TABLE private_extra (value TEXT)", "DELETE FROM fleet_floor"):
            with self.subTest(sql=sql):
                connection = sqlite3.connect(self.path)
                try:
                    connection.execute(sql)
                    connection.commit()
                finally:
                    connection.close()
                with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
                    store.read()
                self.path.unlink()
                self.initialize()

    def test_strict_scalar_bounds_and_maximum_values(self):
        store = self.initialize()
        for field, values in (
            ("minimum_version", (True, 3.0, 0, -1, 2**31, None)),
            ("minimum_time_s", (True, 1000.0, -1, 2**53, None)),
        ):
            for value in values:
                with self.subTest(field=field, value=value):
                    args = {"minimum_version": 3, "minimum_time_s": 1000, field: value}
                    with self.assertRaisesRegex(ValueError, "^invalid_fleet_floor$"):
                        store.advance(**args)
        result = store.advance(minimum_version=2**31 - 1, minimum_time_s=2**53 - 1)
        self.assertEqual((result.minimum_version, result.minimum_time_s), (2**31 - 1, 2**53 - 1))


if __name__ == "__main__":
    unittest.main()
