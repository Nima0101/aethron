"""Publication preflight must inspect the selected Git tree, not local files."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/public_links.py"


class PublicLinks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def tree(self, *paths):
        self.git("add", "--", *paths)
        return self.git("write-tree")

    def check(self, tree):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), tree, "--repo", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertTrue(result.stdout.startswith("{"), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_untracked_files_cannot_satisfy_public_links(self):
        (self.root / "README.md").write_text("[guide](guide.md)\n")
        (self.root / "guide.md").write_text("[evidence](evidence.json)\n")
        (self.root / "evidence.json").write_text("{}\n")
        first = self.tree("README.md")
        code, report = self.check(first)
        self.assertEqual(code, 1)
        self.assertEqual(report["missing"], [{"source": "README.md", "target": "guide.md"}])
        second = self.tree("guide.md")
        code, report = self.check(second)
        self.assertEqual(code, 1)
        self.assertEqual(report["missing"], [{"source": "guide.md", "target": "evidence.json"}])
        third = self.tree("evidence.json")
        self.assertEqual(self.check(third)[0], 0)
        self.assertEqual(self.check(first)[0], 1)

    def test_dirty_worktree_does_not_change_selected_tree(self):
        (self.root / "README.md").write_text(
            "[guide](folder/guide.md#usage)\n[folder](folder)\n[site](https://example.org)\n[section](#local)\n"
        )
        (self.root / "folder").mkdir()
        (self.root / "folder/guide.md").write_text("[root](../README.md)\n")
        tree = self.tree("README.md", "folder")
        (self.root / "README.md").write_text("[missing](private.md)\n")
        (self.root / "folder/guide.md").unlink()
        code, report = self.check(tree)
        self.assertEqual(code, 0)
        self.assertEqual(report["tree"], tree)
        self.assertEqual(report["missing"], [])

    def test_symlink_markdown_cannot_hide_unchecked_content(self):
        (self.root / "link-target").write_text("private-untracked.md")
        oid = self.git("hash-object", "-w", "link-target")
        self.git("update-index", "--add", "--cacheinfo", "120000", oid, "README.md")
        tree = self.git("write-tree")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), tree, "--repo", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "invalid_public_tree\n")

    def test_invalid_revision_returns_no_success_report(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "not-a-valid-ref", "--repo", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
