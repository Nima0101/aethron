"""Bounded synthetic checkout scans; no product child process is executed."""

import contextlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class ScanLimits(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    def reject(self, output, calls, message):
        with self.assertRaisesRegex(ValueError, "^" + message + "$"):
            verify.run()
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(len(calls), 1)

    def test_source_limit_counts_utf8_bytes_before_parse(self):
        for source in ("#é\n", "#éx\n"):
            with self.subTest(source=source), self.fixture(source) as (output, calls):
                with patch.object(verify, "MAX_SOURCE_BYTES", 4, create=True):
                    if len(source.encode()) == 4:
                        verify.run()
                    else:
                        self.reject(output, calls, "source_scan_limit")

    def test_source_total_includes_multiple_files(self):
        for limit in (6, 5):
            with self.subTest(limit=limit), self.fixture("#a\n") as (output, calls):
                (verify.ROOT / "aethron/second.py").write_bytes(b"#b\n")
                with patch.object(verify, "MAX_SOURCE_TOTAL_BYTES", limit, create=True):
                    if limit == 6:
                        verify.run()
                    else:
                        self.reject(output, calls, "source_scan_limit")

    def test_other_text_oversize_rejected_before_open(self):
        with self.fixture("pass\n") as (output, calls):
            target = verify.ROOT / "docs/example.txt"
            target.write_bytes(b"x" * 32 + b"\xff")
            original = Path.open

            def opened(path, *args, **kwargs):
                if path == target:
                    self.fail("oversize text was opened")
                return original(path, *args, **kwargs)

            with (
                patch.object(verify, "MAX_OTHER_TEXT_BYTES", 32, create=True),
                patch.object(Path, "open", opened),
            ):
                self.reject(output, calls, "content_scan_limit")

    def test_other_text_total_spans_roots_and_resets_per_run(self):
        for excess in (False, True):
            with self.subTest(excess=excess), self.fixture("pass\n") as (output, calls):
                (verify.ROOT / "README.txt").write_bytes(b"root")
                (verify.ROOT / "docs/second.txt").write_bytes(b"nested")
                total = sum(p.stat().st_size for p in verify.ROOT.rglob("*") if p.is_file())
                with patch.object(
                    verify, "MAX_OTHER_TEXT_TOTAL_BYTES", total - excess, create=True
                ):
                    if excess:
                        self.reject(output, calls, "content_scan_limit")
                    else:
                        verify.run()
                        verify.run()
                        self.assertEqual(len(calls), 10)

    def test_traversal_counts_ignored_entries_and_closes_on_excess(self):
        with self.fixture("pass\n"):
            base = verify.ROOT / "docs"
            (base / "build").mkdir()
            # Both verification/ and excluded build/ consume enumeration work.
            streams = []
            original = os.scandir

            @contextlib.contextmanager
            def observed(path):
                with original(path) as stream:
                    streams.append(stream)
                    yield stream

            with (
                patch.object(verify, "MAX_TRAVERSAL_ENTRIES", 1, create=True),
                patch.object(os, "scandir", observed),
                self.assertRaisesRegex(ValueError, "^worktree_traversal_limit$"),
            ):
                list(verify.working_files(base, included=set(), recursive=False))
            self.assertEqual(len(streams), 1)
            self.assertEqual(list(streams[0]), [])

    def test_depth_excess_rejects_instead_of_pruning(self):
        for limit in (2, 1):
            with self.subTest(limit=limit), self.fixture("pass\n"):
                base = verify.ROOT / "aethron"
                (base / "nested").mkdir()
                target = base / "nested/example.py"
                target.write_bytes(b"pass\n")
                with patch.object(verify, "MAX_TRAVERSAL_DEPTH", limit, create=True):
                    if limit == 2:
                        self.assertIn(target, list(verify.working_files(base)))
                    else:
                        with self.assertRaisesRegex(ValueError, "^worktree_traversal_limit$"):
                            list(verify.working_files(base))

    def test_entry_budget_is_shared_across_roots_and_resets(self):
        with self.fixture("pass\n") as (output, calls):
            original = os.scandir
            count = 0

            @contextlib.contextmanager
            def observed(path):
                nonlocal count
                with original(path) as stream:

                    def entries():
                        nonlocal count
                        for entry in stream:
                            count += 1
                            yield entry

                    yield entries()

            with patch.object(os, "scandir", observed):
                verify.run()
            total = count
            self.assertGreater(total, 1)
            with patch.object(verify, "MAX_TRAVERSAL_ENTRIES", total, create=True):
                verify.run()
                verify.run()
            output.seek(0)
            output.truncate(0)
            calls.clear()
            with patch.object(verify, "MAX_TRAVERSAL_ENTRIES", total - 1, create=True):
                self.reject(output, calls, "worktree_traversal_limit")
