"""Discovery faults in synthetic checkouts; product children are intercepted."""

import contextlib
import errno
import glob
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class WorkingTreeDiscovery(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    @contextlib.contextmanager
    def instrument_scandir(self, callback):
        # CPython 3.13 glob caches os.scandir when its module is imported.
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(os, "scandir", side_effect=callback))
            if hasattr(glob, "_StringGlobber"):
                stack.enter_context(
                    patch.object(glob._StringGlobber, "scandir", side_effect=callback)
                )
            yield

    def test_scan_errors_prevent_success(self):
        for name in ("aethron", "aethron/nested", "docs", "docs/nested"):
            for code in (errno.EACCES, errno.EIO):
                with (
                    self.subTest(name=name, code=code),
                    self.fixture("value = 1") as (
                        output,
                        calls,
                    ),
                ):
                    blocked = verify.ROOT / name
                    blocked.mkdir(exist_ok=True)
                    scandir = os.scandir
                    attempted = []

                    def fail(
                        path, attempted=attempted, blocked=blocked, code=code, scandir=scandir
                    ):
                        attempted.append(Path(path))
                        if Path(path) == blocked:
                            raise OSError(code, "synthetic enumeration failure")
                        return scandir(path)

                    with self.instrument_scandir(fail):
                        try:
                            with self.assertRaises(OSError) as caught:
                                verify.run()
                        finally:
                            self.assertIn(blocked, attempted)
                    self.assertEqual(caught.exception.errno, code)
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(len(calls), 1)

    def test_untracked_generated_directories_are_not_enumerated(self):
        for generated in ("build", "node_modules", "__pycache__"):
            with self.subTest(generated=generated), self.fixture("value = 1") as (_, calls):
                excluded = verify.ROOT / "docs" / generated
                (excluded / "nested").mkdir(parents=True)
                (excluded / "nested/private.txt").write_text("synthetic", encoding="utf-8")
                scanned = []
                scandir = os.scandir

                def record(path, scanned=scanned, scandir=scandir):
                    scanned.append(Path(path))
                    return scandir(path)

                with self.instrument_scandir(record):
                    verify.run()
                self.assertIn(verify.ROOT / "docs", scanned)
                self.assertFalse(any(p == excluded or excluded in p.parents for p in scanned))
                self.assertEqual(len(calls), 5)

    def test_tracked_descendant_is_checked_without_scanning_untracked_siblings(self):
        with self.fixture("value = 1") as (output, calls):
            name = "docs/build/nested/example.txt"
            target = verify.ROOT / name
            target.parent.mkdir(parents=True)
            target.write_text("synthetic", encoding="utf-8")
            excluded = verify.ROOT / "docs/build/untracked"
            excluded.mkdir()
            scanned = []
            scandir = os.scandir

            def record(path, scanned=scanned, scandir=scandir):
                scanned.append(Path(path))
                return scandir(path)

            with (
                patch.object(verify, "git_output", return_value=(name + "\0").encode()),
                self.instrument_scandir(record),
            ):
                verify.run()
                self.assertIn(target.parent, scanned)
                self.assertNotIn(excluded, scanned)
                output.seek(0)
                output.truncate(0)
                calls.clear()
                target.write_text("BEGIN " + "PRIVATE KEY", encoding="utf-8")
                with self.assertRaisesRegex(AssertionError, "public leak"):
                    verify.run()
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(len(calls), 1)

    def test_iteration_error_after_partial_listing_prevents_success(self):
        with self.fixture("value = 1") as (output, calls):
            blocked = verify.ROOT / "docs/nested"
            blocked.mkdir()
            (blocked / "example.txt").write_text("synthetic", encoding="utf-8")
            scandir = os.scandir
            yielded = []

            @contextlib.contextmanager
            def partial(path):
                with scandir(path) as entries:
                    if Path(path) == blocked:

                        def interrupted():
                            entry = next(entries)
                            yielded.append(entry.name)
                            yield entry
                            raise OSError(errno.EIO, "synthetic partial enumeration")

                        yield interrupted()
                    else:
                        yield entries

            with self.instrument_scandir(partial), self.assertRaises(OSError) as caught:
                verify.run()
            self.assertEqual(yielded, ["example.txt"])
            self.assertEqual(caught.exception.errno, errno.EIO)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_file_cannot_substitute_for_a_scan_root(self):
        with self.fixture("value = 1") as (output, calls):
            (verify.ROOT / "integrations").write_text("synthetic", encoding="utf-8")
            with self.assertRaises(NotADirectoryError):
                verify.run()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_source_rules_still_cover_generated_directories(self):
        with self.fixture("value = 1") as (output, calls):
            target = verify.ROOT / "aethron/build/example.py"
            target.parent.mkdir()
            target.write_text("import socket", encoding="utf-8")
            with self.assertRaises(AssertionError):
                verify.run()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_missing_optional_roots_remain_allowed(self):
        with self.fixture("value = 1") as (_, calls):
            verify.run()
            self.assertEqual(len(calls), 5)
