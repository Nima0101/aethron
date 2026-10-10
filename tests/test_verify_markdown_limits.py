"""Small real-file admission regressions; product children are intercepted."""

import contextlib
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class WorktreeMarkdownLimits(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    @contextlib.contextmanager
    def limits(self, **overrides):
        values = {
            "MAX_WORKTREE_MARKDOWN_BYTES": 128,
            "MAX_WORKTREE_MARKDOWN_TOTAL_BYTES": 256,
            "MAX_WORKTREE_MARKDOWN_DOCUMENTS": 4,
            "MAX_WORKTREE_LOCAL_DESTINATIONS": 4,
        }
        values.update(overrides)
        with patch.multiple(verify, create=True, **values):
            yield

    def reject(self, output, calls):
        with self.assertRaisesRegex(ValueError, "^worktree_markdown_limit$"):
            verify.run()
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(len(calls), 1)

    def test_document_bytes_exact_boundary_and_utf8_overflow(self):
        for body in (b"abcd", "éé".encode(), "ééx".encode()):
            with self.subTest(body=body), self.fixture("value = 1") as (output, calls):
                (verify.ROOT / "docs/a.md").write_bytes(body)
                with self.limits(MAX_WORKTREE_MARKDOWN_BYTES=4):
                    if len(body) == 4:
                        verify.run()
                        self.assertEqual(len(calls), 5)
                    else:
                        self.reject(output, calls)

    def test_oversize_is_rejected_before_open_or_decode(self):
        with self.fixture("value = 1") as (output, calls):
            target = verify.ROOT / "docs/a.md"
            target.write_bytes(b"abcde\xff")
            original = Path.open

            def observed(path, *args, **kwargs):
                if path == target:
                    self.fail("oversize Markdown was opened")
                return original(path, *args, **kwargs)

            with self.limits(MAX_WORKTREE_MARKDOWN_BYTES=4), patch.object(Path, "open", observed):
                self.reject(output, calls)

    def test_document_count_charges_empty_untracked_files(self):
        for count in (2, 3):
            with self.subTest(count=count), self.fixture("value = 1") as (output, calls):
                for i in range(count):
                    (verify.ROOT / f"docs/{i}.md").write_bytes(b"")
                with self.limits(MAX_WORKTREE_MARKDOWN_DOCUMENTS=2):
                    if count == 2:
                        verify.run()
                        self.assertEqual(len(calls), 5)
                    else:
                        self.reject(output, calls)

    def test_total_bytes_span_root_and_nested_files(self):
        for limit in (8, 7):
            with self.subTest(limit=limit), self.fixture("value = 1") as (output, calls):
                for name in ("README.md", "docs/a.md"):
                    (verify.ROOT / name).write_bytes(b"abcd")
                with self.limits(MAX_WORKTREE_MARKDOWN_TOTAL_BYTES=limit):
                    if limit == 8:
                        verify.run()
                        self.assertEqual(len(calls), 5)
                    else:
                        self.reject(output, calls)

    def test_destinations_charge_repeated_existing_paths(self):
        for limit in (2, 1):
            with self.subTest(limit=limit), self.fixture("value = 1") as (output, calls):
                for name in ("README.md", "docs/a.md"):
                    (verify.ROOT / name).write_text("[directory](.)", encoding="utf-8")
                with self.limits(MAX_WORKTREE_LOCAL_DESTINATIONS=limit):
                    if limit == 2:
                        verify.run()
                        self.assertEqual(len(calls), 5)
                    else:
                        self.reject(output, calls)

    def test_excess_destination_is_rejected_before_target_lookup(self):
        with self.fixture("value = 1") as (output, calls):
            (verify.ROOT / "docs/a.md").write_text(
                "[directory](.) [missing](absent.md)", encoding="utf-8"
            )
            with self.limits(MAX_WORKTREE_LOCAL_DESTINATIONS=1):
                self.reject(output, calls)

    def test_read_is_bounded_even_if_file_grows_after_stat(self):
        with self.fixture("value = 1") as (output, calls):
            target = verify.ROOT / "docs/a.md"
            target.write_bytes(b"a")
            original = Path.open
            reads = []

            @contextlib.contextmanager
            def observed(path, *args, **kwargs):
                if path == target:
                    with original(path, "ab") as stream:
                        stream.write(b"b" * 32)
                with original(path, *args, **kwargs) as stream:
                    if path != target:
                        yield stream
                    else:

                        class Reader:
                            def read(self, size=-1):
                                reads.append(size)
                                return stream.read(size)

                        yield Reader()

            with self.limits(MAX_WORKTREE_MARKDOWN_BYTES=4), patch.object(Path, "open", observed):
                self.reject(output, calls)
            self.assertEqual(reads, [5])

    def test_budget_resets_between_invocations(self):
        with self.fixture("value = 1") as (_, calls):
            (verify.ROOT / "docs/a.md").write_bytes(b"abcd")
            with self.limits(
                MAX_WORKTREE_MARKDOWN_DOCUMENTS=1, MAX_WORKTREE_MARKDOWN_TOTAL_BYTES=4
            ):
                verify.run()
                verify.run()
            self.assertEqual(len(calls), 10)
