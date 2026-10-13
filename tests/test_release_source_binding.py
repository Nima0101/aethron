"""Release payloads must belong to the revision named in provenance."""

import hashlib
import json
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import release

REPOSITORY = release.ROOT
GIT_OUTPUT = subprocess.check_output


class ReleaseSourceBinding(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()
        self.committed = {
            "LICENSE": b"synthetic license\n",
            "NOTICE": b"synthetic notice\n",
            "aethron/models/rules.json": b'{"synthetic":true}\n',
            "aethron/payload.bin": b"\x00\xff\nblob 123\n",
        }
        self.revision = "a" * 40
        self.objects = {
            name: hashlib.sha1(
                b"blob " + str(len(data)).encode() + b"\0" + data, usedforsecurity=False
            ).hexdigest()
            for name, data in self.committed.items()
        }
        self.dirty = b""
        self.mode = b"100644"
        self.batch_requests = 0
        for name, data in self.committed.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for patcher in (
            patch.object(release, "ROOT", self.root),
            patch.object(release.subprocess, "check_output", side_effect=self.git),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def git(self, args, **kwargs):
        command = args[1:]
        # Both the old working-tree reader and the corrected object reader use
        # this same committed fixture. No repository or real release is created.
        if command == ["ls-files", "-z"]:
            return b"\0".join(name.encode() for name in sorted(self.committed)) + b"\0"
        if command == ["rev-parse", "HEAD"]:
            return self.revision + "\n"
        if command == ["status", "--porcelain", "--untracked-files=normal"]:
            return self.dirty
        if command == ["ls-tree", "-r", "-z", "--full-tree", self.revision]:
            return b"".join(
                self.mode + b" blob " + self.objects[name].encode() + b"\t" + name.encode() + b"\0"
                for name in sorted(self.committed)
            )
        if command == ["cat-file", "--batch"]:
            self.batch_requests += 1
            by_oid = {self.objects[name]: data for name, data in self.committed.items()}
            return b"".join(
                oid
                + b" blob "
                + str(len(by_oid[oid.decode()])).encode()
                + b"\n"
                + by_oid[oid.decode()]
                + b"\n"
                for oid in kwargs["input"].splitlines()
            )
        self.fail(f"unexpected Git command: {command}")

    def test_worktree_change_after_clean_check_cannot_enter_release(self):
        (self.root / "aethron/models/rules.json").write_bytes(b"uncommitted replacement")
        destination = Path(self.temporary.name) / "release"
        release.build(destination)
        manifest = json.loads((destination / "source-manifest.json").read_text())
        self.assertEqual(
            manifest,
            {name: hashlib.sha256(data).hexdigest() for name, data in self.committed.items()},
        )
        with tarfile.open(destination / "aethron-0.2.0-source.tar.gz") as archive:
            for name, data in self.committed.items():
                self.assertEqual(archive.extractfile("aethron-0.2.0/" + name).read(), data)
        with zipfile.ZipFile(destination / "aethron.pyz") as archive:
            self.assertEqual(
                archive.read("aethron/models/rules.json"),
                self.committed["aethron/models/rules.json"],
            )
        self.assertEqual(
            json.loads((destination / "provenance.json").read_text())["source_revision"],
            self.revision,
        )

    def test_missing_worktree_payload_preserves_source_admission(self):
        (self.root / "aethron/payload.bin").unlink()
        destination = Path(self.temporary.name) / "release"
        with self.assertRaisesRegex(SystemExit, "release source unavailable"):
            release.build(destination)
        self.assertFalse(destination.exists())
        self.assertEqual(self.batch_requests, 0)

    def test_dirty_worktree_still_blocks_release(self):
        self.dirty = b" M aethron/payload.bin\n"
        destination = Path(self.temporary.name) / "release"
        with self.assertRaisesRegex(SystemExit, "clean committed source"):
            release.build(destination)
        self.assertFalse(destination.exists())
        self.assertEqual(self.batch_requests, 0)

    def test_link_or_submodule_is_rejected_before_reading_payloads(self):
        for mode in (b"120000", b"160000"):
            with self.subTest(mode=mode):
                self.mode = mode
                destination = Path(self.temporary.name) / "release"
                with self.assertRaisesRegex(ValueError, "release_requires_regular_blobs"):
                    release.build(destination)
                self.assertFalse(destination.exists())
                self.assertEqual(self.batch_requests, 0)

    def test_actual_git_object_reader_without_creating_a_repository(self):
        revision = GIT_OUTPUT(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True).strip()
        expected = GIT_OUTPUT(["git", "show", revision + ":LICENSE"], cwd=REPOSITORY)

        def only_license(args, **kwargs):
            if args[1] == "ls-tree":
                args = [*args, "--", "LICENSE"]
            return GIT_OUTPUT(args, **kwargs)

        with (
            patch.object(release, "ROOT", REPOSITORY),
            patch.object(release.subprocess, "check_output", side_effect=only_license),
        ):
            self.assertEqual(release.committed_blobs(revision), {"LICENSE": expected})


if __name__ == "__main__":
    unittest.main()
