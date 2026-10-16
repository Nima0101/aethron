"""Repository containment checks with synthetic files and intercepted children."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from scripts import verify
from tests import test_verify_static as static_checks


class WorkingTreePaths(unittest.TestCase):
    # Reuse only the fixture, not its unrelated test methods.
    fixture = static_checks.StaticCheckClaims.fixture

    def assert_rejected_without_external_read(self):
        opened = []
        original_open = Path.open

        def observed_open(path, *args, **kwargs):
            if not path.resolve().is_relative_to(verify.ROOT.resolve()):
                opened.append(path)
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", observed_open):
            with self.assertRaisesRegex(AssertionError, "^unsafe repository path$"):
                verify.run()
        self.assertEqual(opened, [])

    def test_symlinks_rejected_before_content_reads(self):
        for name in (
            "aethron/example.py",
            "docs/example.md",
            "docs/verification/governance-freeze.json",
        ):
            with self.subTest(name=name), self.fixture("value = 1") as (output, _):
                with tempfile.TemporaryDirectory() as outside:
                    target = Path(outside) / "synthetic"
                    target.write_text('{"files": {}}\n', encoding="utf-8")
                    link = verify.ROOT / name
                    link.unlink(missing_ok=True)
                    link.symlink_to(target)
                    self.assert_rejected_without_external_read()
                    self.assertEqual(output.getvalue(), "")

    def test_symlink_directories_rejected(self):
        for name in ("integrations", "docs/alias"):
            with self.subTest(name=name), self.fixture("value = 1"):
                with tempfile.TemporaryDirectory() as outside:
                    (Path(outside) / "example.txt").write_text("Synthetic.\n", encoding="utf-8")
                    (verify.ROOT / name).symlink_to(outside, target_is_directory=True)
                    self.assert_rejected_without_external_read()

    def test_freeze_entries_cannot_read_outside_checkout(self):
        for absolute in (False, True):
            with self.subTest(absolute=absolute), self.fixture("value = 1"):
                with tempfile.TemporaryDirectory(dir=verify.ROOT.parent) as outside:
                    target = Path(outside) / "synthetic.txt"
                    target.write_bytes(b"Synthetic freeze bytes.\n")
                    name = (
                        str(target) if absolute else "../" + target.parent.name + "/synthetic.txt"
                    )
                    manifest = verify.ROOT / "docs/verification/governance-freeze.json"
                    manifest.write_text(
                        json.dumps(
                            {"files": {name: hashlib.sha256(target.read_bytes()).hexdigest()}}
                        ),
                        encoding="utf-8",
                    )
                    self.assert_rejected_without_external_read()

    def test_links_cannot_be_satisfied_outside_checkout(self):
        for absolute in (False, True):
            with self.subTest(absolute=absolute), self.fixture("value = 1"):
                with tempfile.TemporaryDirectory(dir=verify.ROOT.parent) as outside:
                    target = Path(outside) / "synthetic.txt"
                    target.write_text("Synthetic.\n", encoding="utf-8")
                    name = (
                        str(target)
                        if absolute
                        else "../../" + target.parent.name + "/synthetic.txt"
                    )
                    (verify.ROOT / "docs/example.md").write_text(
                        f"[outside]({quote(name, safe='')})\n", encoding="utf-8"
                    )
                    self.assert_rejected_without_external_read()

    def test_parent_relative_link_inside_checkout_still_passes(self):
        with self.fixture("value = 1") as (_, calls):
            (verify.ROOT / "target.txt").write_text("Synthetic.\n", encoding="utf-8")
            (verify.ROOT / "docs/example.md").write_text(
                "[inside](../target.txt)\n", encoding="utf-8"
            )
            verify.run()
            self.assertEqual(len(calls), 5)
