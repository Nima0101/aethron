"""Archive format evidence from tiny synthetic files, never a product build."""

import hashlib
import json
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import release


class ReleaseArchive(unittest.TestCase):
    def fixture(self, root):
        source = root / "source"
        blobs = {
            "LICENSE": b"synthetic license fixture\n",
            "NOTICE": b"synthetic notice fixture\n",
            "aethron/__init__.py": b"# synthetic placeholder, not executed\n",
            "aethron/models/rules.json": b"{}\n",
            "notes.bin": bytes(range(256)),
        }
        for name, data in blobs.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return source, blobs

    def build_fixture(self, source, blobs, destination):
        def git_output(args, **kwargs):
            if args[1:] == ["ls-files", "-z"]:
                return ("\0".join(reversed(list(blobs))) + "\0").encode()
            if args[1:] == ["rev-parse", "HEAD"]:
                return "a" * 40 + "\n"
            if args[1:] == ["status", "--porcelain", "--untracked-files=normal"]:
                return b""
            self.fail(f"unexpected Git request: {args}")

        with (
            patch.object(release, "ROOT", source),
            patch.object(release, "committed_blobs", return_value=dict(sorted(blobs.items()))),
            patch.object(release.subprocess, "check_output", side_effect=git_output),
        ):
            release.build(destination)

    def test_bytes_preserved_with_normalized_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, blobs = self.fixture(root)
            first, second = root / "first", root / "second"
            self.build_fixture(source, blobs, first)
            for name in blobs:
                path = source / name
                path.chmod(0o755)
                os.utime(path, (946684800, 946684800))
            self.build_fixture(source, blobs, second)
            self.assertEqual(
                {p.name: p.read_bytes() for p in first.iterdir()},
                {p.name: p.read_bytes() for p in second.iterdir()},
            )
            with tarfile.open(first / "aethron-0.2.0-source.tar.gz", "r:gz") as archive:
                self.assertEqual(archive.getnames(), ["aethron-0.2.0/" + n for n in sorted(blobs)])
                for member in archive.getmembers():
                    self.assertTrue(member.isfile())
                    self.assertEqual((member.mode, member.mtime), (0o644, 0))
                    self.assertEqual(
                        (member.uid, member.gid, member.uname, member.gname), (0, 0, "", "")
                    )
                    with archive.extractfile(member) as stream:
                        self.assertEqual(
                            stream.read(), blobs[member.name.removeprefix("aethron-0.2.0/")]
                        )
            with zipfile.ZipFile(first / "aethron.pyz") as archive:
                expected = [
                    "LICENSE",
                    "NOTICE",
                    "__main__.py",
                    "aethron/__init__.py",
                    "aethron/models/rules.json",
                ]
                self.assertEqual(archive.namelist(), expected)
                for member in archive.infolist():
                    self.assertEqual(member.date_time, (2026, 1, 1, 0, 0, 0))
                    self.assertEqual(member.external_attr >> 16, 0o644)
                    self.assertEqual(member.compress_type, zipfile.ZIP_STORED)
                    if member.filename != "__main__.py":
                        self.assertEqual(archive.read(member), blobs[member.filename])
            self.assertEqual({n: (source / n).read_bytes() for n in blobs}, blobs)

    def test_unrepresentable_ustar_name_fails_without_truncating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, blobs = self.fixture(root)
            name = "x" * 101
            blobs[name] = b"long-name synthetic fixture"
            (source / name).write_bytes(blobs[name])
            destination = root / "output"
            with self.assertRaises(ValueError):
                self.build_fixture(source, blobs, destination)
            self.assertFalse((destination / "aethron-0.2.0-source.tar.gz").exists())
            self.assertEqual({n: (source / n).read_bytes() for n in blobs}, blobs)

    def test_zip_creator_default_cannot_change_artifacts(self):
        initialize = zipfile.ZipInfo.__init__
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, blobs = self.fixture(root)
            builds = []
            for creator in (0, 3):

                def host_initialize(info, *args, creator=creator, **kwargs):
                    initialize(info, *args, **kwargs)
                    info.create_system = creator

                destination = root / str(creator)
                with patch.object(zipfile.ZipInfo, "__init__", host_initialize):
                    self.build_fixture(source, blobs, destination)
                builds.append({p.name: p.read_bytes() for p in destination.iterdir()})
                with zipfile.ZipFile(destination / "aethron.pyz") as archive:
                    self.assertIsNone(archive.testzip())
                    for member in archive.infolist():
                        self.assertEqual(member.create_system, 3)
                        self.assertEqual(member.external_attr >> 16, 0o644)
            self.assertEqual(builds[0], builds[1])

    def test_text_newline_default_cannot_change_artifacts(self):
        open_path = Path.open
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, blobs = self.fixture(root)
            builds = []
            for index, line_ending in enumerate(("\n", "\r\n")):

                def host_open(
                    path,
                    mode="r",
                    buffering=-1,
                    encoding=None,
                    errors=None,
                    newline=None,
                    *,
                    line_ending=line_ending,
                ):
                    if "b" not in mode and "w" in mode and newline is None:
                        newline = line_ending
                    return open_path(path, mode, buffering, encoding, errors, newline)

                destination = root / str(index)
                with patch.object(Path, "open", host_open):
                    self.build_fixture(source, blobs, destination)
                artifacts = {p.name: p.read_bytes() for p in destination.iterdir()}
                builds.append(artifacts)
                for name in (
                    "source-manifest.json",
                    "sbom.cdx.json",
                    "provenance.json",
                    "SHA256SUMS",
                ):
                    with self.subTest(line_ending=line_ending, artifact=name):
                        self.assertNotIn(b"\r", artifacts[name])
                        self.assertTrue(artifacts[name].endswith(b"\n"))
                provenance = json.loads(artifacts["provenance.json"])
                self.assertEqual(
                    provenance["source_manifest_sha256"],
                    hashlib.sha256(artifacts["source-manifest.json"]).hexdigest(),
                )
                for row in artifacts["SHA256SUMS"].decode("utf-8").splitlines():
                    digest, name = row.split("  ")
                    self.assertEqual(digest, hashlib.sha256(artifacts[name]).hexdigest())
            self.assertEqual(builds[0], builds[1])
