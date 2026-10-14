"""Source releases must not certify case-colliding paths on Linux either."""

import gzip
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release, reproduce

ALIASES = (
    ("Module.py", "module.py"),
    ("source/Module.py", "source/module.py"),
    ("Source/first.txt", "source/second.txt"),
    ("Source", "source/child.txt"),
    ("source/Café.txt", "source/CAFÉ.txt"),
    ("Straße/first.txt", "STRASSE/second.txt"),
)


class ReleaseCaseAliases(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "-q")
        self.blob = self.git("hash-object", "-w", "--stdin", data=b"payload\n")

    def git(self, *args, data=None):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, input=data, stderr=subprocess.PIPE, timeout=10
        ).strip()

    def tree(self, paths):
        children = {}
        for path in paths:
            first, _, rest = path.partition("/")
            children.setdefault(first, []).append(rest)
        records = []
        for name, descendants in children.items():
            if descendants == [""]:
                metadata = b"100644 blob " + self.blob
            else:
                metadata = b"040000 tree " + self.tree(descendants)
            records.append(metadata + b"\t" + name.encode())
        return self.git("mktree", "-z", data=b"\0".join(records) + b"\0")

    def assert_tree_rejected(self, tree):
        execute = subprocess.check_output
        with patch.object(release.subprocess, "check_output", wraps=execute) as calls:
            with self.assertRaisesRegex(ValueError, "^release_source_path_alias$"):
                release.committed_blobs(tree.decode(), root=self.root)
        self.assertFalse(any("cat-file" in call.args[0] for call in calls.call_args_list))

    def test_committed_case_aliases_reject_before_payload_reads(self):
        for names in ALIASES:
            with self.subTest(names=names):
                self.assert_tree_rejected(self.tree(names))

    def test_empty_directory_case_aliases_reject(self):
        empty = self.git("mktree", data=b"")
        records = [b"040000 tree " + empty + b"\t" + name for name in (b"Source", b"source")]
        self.assert_tree_rejected(self.git("mktree", "-z", data=b"\0".join(records) + b"\0"))

    def test_checkout_case_aliases_reject_before_filesystem_access(self):
        for names in ALIASES:
            with self.subTest(names=names):

                def git(args, names=names, **kwargs):
                    if "ls-files" in args:
                        return b"\0".join(b"H " + name.encode() for name in names) + b"\0"
                    if "rev-parse" in args:
                        return "a" * 40 + "\n"
                    if "status" in args:
                        return b""
                    self.fail(f"unexpected command: {args}")

                destination = self.root / "release"
                with (
                    patch.object(release, "ROOT", self.root),
                    patch.object(release.subprocess, "check_output", side_effect=git),
                    patch.object(Path, "lstat", side_effect=AssertionError("source inspected")),
                    patch.object(release, "committed_blobs") as blobs,
                ):
                    with self.assertRaisesRegex(ValueError, "^release_source_path_alias$"):
                        release.build(destination)
                blobs.assert_not_called()
                self.assertFalse(destination.exists())

    def archive(self, names):
        data = b"payload\n"
        manifest = json.dumps({name: hashlib.sha256(data).hexdigest() for name in names}).encode()
        buffer = io.BytesIO()
        with tarfile.open(
            fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT, encoding="utf-8"
        ) as archive:
            for name in names:
                member = tarfile.TarInfo("aethron-0.2.0/" + name)
                member.mode = 0o644
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0, compresslevel=9) as stream:
            stream.write(buffer.getvalue())
        return compressed.getvalue(), manifest

    def test_case_colliding_archives_do_not_qualify(self):
        for names in ALIASES:
            for ordered in (names, names[::-1]):
                with self.subTest(names=ordered):
                    with self.assertRaisesRegex(ValueError, "^release_source_archive_invalid$"):
                        reproduce.validate_source_archive(*self.archive(ordered))

    def test_unique_mixed_case_paths_preserve_spelling_and_payload(self):
        names = ("Source/Module.py", "Source/Café.txt", "Other/module.py", "Straße/data.txt")
        self.assertEqual(
            release.committed_blobs(self.tree(names).decode(), root=self.root),
            dict.fromkeys(names, b"payload\n"),
        )
        archive, manifest = self.archive(names)
        self.assertEqual(reproduce.validate_source_archive(archive, manifest), json.loads(manifest))


if __name__ == "__main__":
    unittest.main()
