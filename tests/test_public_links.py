"""Publication preflight must inspect the selected Git tree, not local files."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_verify_links import CASES

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/public_links.py"


class PublicLinks(unittest.TestCase):
    def test_markdown_destinations_match_worktree_semantics(self):
        for text, targets, missing in CASES:
            with self.subTest(text=text):
                (self.root / "README.md").write_text(text, encoding="utf-8")
                for target in targets:
                    (self.root / target).write_text("synthetic", encoding="utf-8")
                tree = self.tree("README.md", *targets)
                code, report = self.check(tree)
                self.assertEqual(code, int(missing))
                self.assertEqual(bool(report["missing"]), missing)

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

    def invoke(self, tree):
        return subprocess.run(
            [sys.executable, str(SCRIPT), tree, "--repo", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    def check(self, tree):
        result = self.invoke(tree)
        self.assertTrue(result.stdout.startswith("{"), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def assert_invalid(self, revision):
        result = self.invoke(revision)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "invalid_public_tree\n")

    def test_invalid_utf8_document_returns_no_report(self):
        (self.root / "README.md").write_bytes(b"invalid: \xff\n")
        self.assert_invalid(self.tree("README.md"))

    def test_excessive_nesting_returns_no_partial_missing_report(self):
        (self.root / "README.md").write_text(
            "[missing](first.md)\n\n" + "> " * 64 + "[missing](second.md)\n",
            encoding="utf-8",
        )
        self.assert_invalid(self.tree("README.md"))

    def object_tree(self, entries):
        return (
            subprocess.check_output(
                ["git", "mktree", "-z"],
                input=b"\0".join(entries) + b"\0",
                cwd=self.root,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            .decode()
            .strip()
        )

    def test_invalid_utf8_tree_paths_return_no_report(self):
        (self.root / "content").write_bytes(b"Synthetic document.\n")
        oid = self.git("hash-object", "-w", "content").encode("ascii")
        for name in (b"bad\xff.md", b"bad\xff.txt"):
            with self.subTest(name=name):
                tree = self.object_tree([b"100644 blob " + oid + b"\t" + name])
                self.assert_invalid(tree)

    def test_nul_inventory_preserves_unicode_tabs_and_newlines(self):
        (self.root / "README.md").write_text(
            "[tab](a%09b.txt) [line](a%0Ab.txt) [unicode](r%C3%A4ksm%C3%B6rg%C3%A5s.txt)\n",
            encoding="utf-8",
        )
        oid = self.git("hash-object", "-w", "README.md").encode("ascii")
        names = [b"README.md", b"a\tb.txt", b"a\nb.txt", "räksmörgås.txt".encode("utf-8")]
        tree = self.object_tree([b"100644 blob " + oid + b"\t" + name for name in names])
        self.assertEqual(self.check(tree), (0, {"tree": tree, "missing": []}))

    def test_markdown_named_directory_is_a_container(self):
        (self.root / "docs.md").mkdir()
        (self.root / "README.md").write_text("[directory](docs.md)\n", encoding="utf-8")
        (self.root / "target.txt").write_text("Synthetic target.\n", encoding="utf-8")
        guide = self.root / "docs.md/guide.md"
        guide.write_text("[target](../target.txt)\n", encoding="utf-8")
        tree = self.tree("README.md", "target.txt", "docs.md")
        self.assertEqual(self.check(tree), (0, {"tree": tree, "missing": []}))
        guide.write_text("[missing](../absent.txt)\n", encoding="utf-8")
        changed = self.tree("docs.md")
        self.assertEqual(
            self.check(changed),
            (
                1,
                {
                    "tree": changed,
                    "missing": [{"source": "docs.md/guide.md", "target": "absent.txt"}],
                },
            ),
        )

    def test_missing_local_blob_returns_no_report(self):
        (self.root / "README.md").write_text("Synthetic document.\n", encoding="utf-8")
        tree = self.tree("README.md")
        oid = self.git("rev-parse", tree + ":README.md")
        self.remove_fixture_object(oid)
        self.assert_invalid(tree)

    def remove_fixture_object(self, oid):
        obj = self.root / ".git/objects" / oid[:2] / oid[2:]
        # Git loose objects are read-only; Windows refuses their deletion.
        # Only the disposable fixture object gets its read-only bit cleared.
        obj.chmod(stat.S_IREAD | stat.S_IWRITE)
        obj.unlink()

    def assert_missing_promisor_object_stays_local(self, kind):
        (self.root / "README.md").write_text("Synthetic document.\n", encoding="utf-8")
        tree = self.tree("README.md")
        commit = self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            tree,
            "-m",
            "synthetic",
        )
        self.git("update-ref", "HEAD", commit)
        remote = self.root / "remote.git"
        self.git("clone", "--bare", "--no-hardlinks", "--quiet", str(self.root), str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("config", "remote.origin.promisor", "true")
        self.git("config", "protocol.file.allow", "always")
        oid = {"commit": commit, "tree": tree, "blob": self.git("rev-parse", tree + ":README.md")}[
            kind
        ]
        self.remove_fixture_object(oid)
        trace = self.root / "git-trace.log"
        # Explicitly permissive caller settings must not enable checker fetching.
        with mock.patch.dict(
            os.environ,
            {"GIT_NO_LAZY_FETCH": "0", "GIT_ALLOW_PROTOCOL": "file", "GIT_TRACE": str(trace)},
        ):
            self.assert_invalid(commit)
        self.assertNotIn(" fetch ", trace.read_text(encoding="utf-8"))
        # Positive fixture control: ordinary Git can retrieve this exact object.
        with mock.patch.dict(os.environ, {"GIT_NO_LAZY_FETCH": "0", "GIT_ALLOW_PROTOCOL": "file"}):
            self.assertEqual(self.git("cat-file", "-t", oid), kind)

    def test_missing_promisor_commit_does_not_fetch(self):
        self.assert_missing_promisor_object_stays_local("commit")

    def test_missing_promisor_tree_does_not_fetch(self):
        self.assert_missing_promisor_object_stays_local("tree")

    def test_missing_promisor_blob_does_not_fetch(self):
        self.assert_missing_promisor_object_stays_local("blob")

    def replacement_fixture(self):
        document = self.root / "README.md"
        document.write_text("[missing](absent.md)\n", encoding="utf-8")
        original = self.tree("README.md")
        document.write_text("Synthetic replacement with no links.\n", encoding="utf-8")
        replacement = self.tree("README.md")
        return original, replacement

    def assert_original_missing(self, revision, tree):
        code, report = self.check(revision)
        self.assertEqual(code, 1)
        self.assertEqual(report["tree"], tree)
        self.assertEqual(report["missing"], [{"source": "README.md", "target": "absent.md"}])

    def test_blob_replacement_cannot_hide_broken_link(self):
        original, replacement = self.replacement_fixture()
        original_blob = self.git("rev-parse", original + ":README.md")
        replacement_blob = self.git("rev-parse", replacement + ":README.md")
        self.git("replace", original_blob, replacement_blob)
        self.assertEqual(
            self.git("cat-file", "blob", original_blob), "Synthetic replacement with no links."
        )
        self.assert_original_missing(original, original)

    def test_tree_replacement_cannot_hide_broken_link(self):
        original, replacement = self.replacement_fixture()
        self.git("replace", original, replacement)
        self.assertEqual(self.git("ls-tree", original), self.git("ls-tree", replacement))
        self.assert_original_missing(original, original)

    def test_commit_replacement_cannot_change_selected_tree(self):
        original, replacement = self.replacement_fixture()
        commits = [
            self.git(
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit-tree",
                tree,
                "-m",
                "synthetic",
            )
            for tree in (original, replacement)
        ]
        self.git("replace", *commits)
        self.assertEqual(self.git("rev-parse", commits[0] + "^{tree}"), replacement)
        self.assert_original_missing(commits[0], original)

    def test_parent_paths_and_symlink_targets_use_tree_inventory(self):
        (self.root / "docs").mkdir()
        (self.root / "docs/README.md").write_text(
            "[guide](../guide.txt) [root](..) [outside](../../guide.txt) [alias](../alias.txt)\n",
            encoding="utf-8",
        )
        (self.root / "guide.txt").write_text("Synthetic guide.\n", encoding="utf-8")
        (self.root / "link-target").write_text("guide.txt", encoding="utf-8")
        oid = self.git("hash-object", "-w", "link-target")
        self.git("update-index", "--add", "--cacheinfo", "120000", oid, "alias.txt")
        tree = self.tree("docs/README.md", "guide.txt")
        code, report = self.check(tree)
        self.assertEqual(code, 1)
        self.assertEqual(
            report["missing"],
            [
                {"source": "docs/README.md", "target": "../guide.txt"},
                {"source": "docs/README.md", "target": "alias.txt"},
            ],
        )

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
