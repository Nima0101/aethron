"""Small synthetic Git responses exercise public-tree aggregate budgets."""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import public_links


class PublicLinkLimits(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, documents, extra=()):
        # Equal content deliberately uses the same object ID at different paths.
        oids = {}
        records = []
        for name, body in documents:
            oid = oids.setdefault(body, len(oids))
            records.append(f"100644 blob {oid}\t{name}".encode())
        records.extend(f"100644 blob extra\t{name}".encode() for name in extra)
        inventory = b"\0".join(records) + (b"\0" if records else b"")
        responses = [b"tree\n", inventory, *(body for _, body in documents)]
        with patch.object(public_links, "git_output", side_effect=responses) as git:
            yield git

    def check(self):
        return public_links.check(Path.cwd(), "HEAD")

    def test_entry_limit_stops_before_any_blob_read(self):
        with (
            self.fixture([("a.md", b"ok")], extra=("b.txt",)) as git,
            patch.object(public_links, "MAX_TREE_ENTRIES", 1, create=True),
        ):
            with self.assertRaisesRegex(ValueError, "^public_tree_limit$"):
                self.check()
            self.assertEqual(git.call_count, 2)

    def test_document_limit_stops_before_next_blob_read(self):
        with (
            self.fixture([("a.md", b"ok"), ("b.md", b"ok")]) as git,
            patch.object(public_links, "MAX_MARKDOWN_DOCUMENTS", 1, create=True),
        ):
            with self.assertRaisesRegex(ValueError, "^public_tree_limit$"):
                self.check()
            self.assertLessEqual(git.call_count, 3)

    def test_document_byte_limit_rejects_before_parsing(self):
        with (
            self.fixture([("a.md", "éé".encode())]),
            patch.object(public_links, "MAX_MARKDOWN_BYTES", 3, create=True),
            patch.object(public_links, "local_destinations", return_value=[]) as parse,
        ):
            with self.assertRaisesRegex(ValueError, "^public_tree_limit$"):
                self.check()
            parse.assert_not_called()

    def test_total_document_bytes_are_charged_per_path(self):
        with (
            self.fixture([("a.md", b"ok"), ("b.md", b"ok")]),
            patch.object(public_links, "MAX_TOTAL_MARKDOWN_BYTES", 3, create=True),
            patch.object(public_links, "local_destinations", return_value=[]) as parse,
        ):
            with self.assertRaisesRegex(ValueError, "^public_tree_limit$"):
                self.check()
            self.assertEqual(parse.call_count, 1)

    def test_local_destinations_count_even_when_targets_exist(self):
        with (
            self.fixture([("a.md", b"[one](.) [two](.)")]),
            patch.object(public_links, "MAX_LOCAL_DESTINATIONS", 1, create=True),
        ):
            with self.assertRaisesRegex(ValueError, "^public_tree_limit$"):
                self.check()

    def test_destination_count_is_shared_across_documents(self):
        with (
            self.fixture([("a.md", b"[one](.)"), ("b.md", b"[two](.)")]),
            patch.object(public_links, "MAX_LOCAL_DESTINATIONS", 1, create=True),
        ):
            with self.assertRaisesRegex(ValueError, "^public_tree_limit$"):
                self.check()

    def test_missing_report_bytes_include_source_and_unicode_target(self):
        # UTF-8 fields total 4+2 bytes: a.md and é.
        for budget, fails in ((6, False), (5, True)):
            with (
                self.subTest(budget=budget),
                self.fixture([("a.md", b"[x](%C3%A9)")]),
                patch.object(public_links, "MAX_MISSING_PATH_BYTES", budget, create=True),
            ):
                if fails:
                    with self.assertRaisesRegex(ValueError, "^public_tree_limit$"):
                        self.check()
                else:
                    self.assertEqual(self.check()["missing"], [{"source": "a.md", "target": "é"}])

    def test_exact_limits_preserve_report_and_empty_tree(self):
        with (
            self.fixture([("a.md", b"[x](.)")]),
            patch.object(public_links, "MAX_TREE_ENTRIES", 1, create=True),
            patch.object(public_links, "MAX_MARKDOWN_DOCUMENTS", 1, create=True),
            patch.object(public_links, "MAX_MARKDOWN_BYTES", 6, create=True),
            patch.object(public_links, "MAX_TOTAL_MARKDOWN_BYTES", 6, create=True),
            patch.object(public_links, "MAX_LOCAL_DESTINATIONS", 1, create=True),
        ):
            self.assertEqual(self.check(), {"tree": "tree", "missing": []})
        with self.fixture([]):
            self.assertEqual(self.check(), {"tree": "tree", "missing": []})

    def test_late_budget_failure_cli_emits_no_partial_report(self):
        with (
            self.fixture([("a.md", b"[x](missing) [y](other)")]),
            patch.object(public_links, "MAX_LOCAL_DESTINATIONS", 1, create=True),
            patch.object(sys, "argv", ["public_links.py", "HEAD"]),
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            with self.assertRaises(SystemExit) as caught:
                public_links.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "invalid_public_tree\n")

    def test_missing_report_budget_is_shared_across_documents(self):
        with (
            self.fixture([("a.md", b"[x](missing)"), ("b.md", b"[x](missing)")]),
            patch.object(public_links, "MAX_MISSING_PATH_BYTES", 21, create=True),
        ):
            with self.assertRaisesRegex(ValueError, "^public_tree_limit$"):
                self.check()

    def test_unterminated_inventory_cannot_bypass_entry_accounting(self):
        with (
            patch.object(
                public_links, "git_output", side_effect=[b"tree", b"100644 blob x\ta.txt"]
            ),
            patch.object(public_links, "MAX_TREE_ENTRIES", 0, create=True),
        ):
            with self.assertRaises(ValueError):
                self.check()

    def test_cli_parser_recursion_failure_emits_no_report(self):
        with (
            self.fixture([("a.md", b"synthetic")]),
            patch.object(public_links, "local_destinations", side_effect=RecursionError("private")),
            patch.object(sys, "argv", ["public_links.py", "HEAD"]),
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            with self.assertRaises(SystemExit) as caught:
                public_links.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "invalid_public_tree\n")
