"""Reproduction manifests must name the exact original Git tree and blob bytes."""

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release, reproduce


class ReproductionSourceBinding(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "--quiet")
        self.git("config", "core.autocrlf", "false")
        self.files = {
            ".gitattributes": b"* -text\n",
            "source.txt": b"original source\n",
            "space and unicode é.bin": b"\x00\xff\nblob 123\n",
            "empty.txt": b"",
            "-leading-dash.txt": b"same content\n",
            "nested/same.txt": b"same content\n",
        }
        for name, data in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "original fixture")
        self.revision = self.git("rev-parse", "HEAD")
        self.manifest = {
            name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()
        }

    def git(self, *args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Reproduction Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=" + str(self.root / "no-hooks"),
                *args,
            ],
            cwd=self.root,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        ).strip()

    def test_manifest_uses_supplied_repository_and_original_blob_bytes(self):
        # Mutable checkout bytes (including newline conversion) are not authoritative.
        (self.root / "source.txt").write_bytes(b"original source\r\n")
        with patch.object(release, "ROOT", self.root / "nonexistent-repository"):
            reproduce.validate_source_manifest(self.root, self.revision, self.manifest)
            for defect in ("content", "missing", "extra", "renamed"):
                with self.subTest(defect=defect):
                    manifest = dict(self.manifest)
                    if defect == "content":
                        manifest["source.txt"] = hashlib.sha256(b"original source\r\n").hexdigest()
                    elif defect == "missing":
                        del manifest["source.txt"]
                    elif defect == "extra":
                        manifest["extra.txt"] = manifest["source.txt"]
                    else:
                        manifest["renamed.txt"] = manifest.pop("source.txt")
                    with self.assertRaisesRegex(ValueError, "^release_source_manifest_invalid$"):
                        reproduce.validate_source_manifest(self.root, self.revision, manifest)

    def test_replacement_refs_cannot_substitute_manifest_source(self):
        (self.root / "source.txt").write_bytes(b"replacement source\n")
        self.git("add", "source.txt")
        self.git("commit", "--quiet", "-m", "replacement fixture")
        replacement = self.git("rev-parse", "HEAD")
        changed = dict(
            self.manifest, **{"source.txt": hashlib.sha256(b"replacement source\n").hexdigest()}
        )
        for suffix in (":source.txt", "^{tree}", ""):
            with self.subTest(suffix=suffix):
                original_oid = self.git("rev-parse", self.revision + suffix)
                replacement_oid = self.git("rev-parse", replacement + suffix)
                self.git("replace", original_oid, replacement_oid)
                try:
                    reproduce.validate_source_manifest(self.root, self.revision, self.manifest)
                    with self.assertRaisesRegex(ValueError, "^release_source_manifest_invalid$"):
                        reproduce.validate_source_manifest(self.root, self.revision, changed)
                    self.assertEqual(self.git("replace", "--list"), original_oid)
                finally:
                    self.git("replace", "--delete", original_oid)


if __name__ == "__main__":
    unittest.main()
