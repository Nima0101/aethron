"""Local Git replacement refs must not rewrite release provenance or payloads."""

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


class ReleaseReplacements(unittest.TestCase):
    def test_replacements_cannot_change_original_revision_artifacts(self):
        for kind in ("blob", "tree", "commit"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                source.mkdir()

                def git(*args, source=source):
                    return subprocess.check_output(
                        [
                            "git",
                            "-c",
                            "user.name=Release Fixture",
                            "-c",
                            "user.email=fixture@example.invalid",
                            "-c",
                            "commit.gpgsign=false",
                            "-c",
                            "core.hooksPath=" + str(source / "no-hooks"),
                            *args,
                        ],
                        cwd=source,
                        stderr=subprocess.PIPE,
                        timeout=5,
                    ).strip()

                git("init", "--quiet")
                original = {
                    "LICENSE": b"synthetic license\n",
                    "NOTICE": b"synthetic notice\n",
                    "aethron/models/rules.json": b'{"original":true}\n',
                }
                for name, data in original.items():
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                git("add", ".")
                git("commit", "--quiet", "-m", "original fixture")
                revision = git("rev-parse", "HEAD").decode()
                suffix = {"blob": ":aethron/models/rules.json", "tree": "^{tree}", "commit": ""}
                old = git("rev-parse", revision + suffix[kind]).decode()
                with patch.object(release, "ROOT", source):
                    release.build(root / "baseline")

                (source / "aethron/models/rules.json").write_bytes(b'{"replacement":true}\n')
                git("add", ".")
                git("commit", "--quiet", "-m", "replacement fixture")
                new = git("rev-parse", "HEAD" + suffix[kind]).decode()
                # Only the disposable fixture checkout is restored.
                git("checkout", "--quiet", "--detach", revision)
                git("replace", old, new)
                self.assertEqual(git("rev-parse", "HEAD").decode(), revision)
                self.assertNotEqual(
                    git("show", revision + ":aethron/models/rules.json"),
                    original["aethron/models/rules.json"].strip(),
                )

                with patch.object(release, "ROOT", source):
                    self.assertEqual(release.committed_blobs(revision), original)
                    self.assertEqual(release.build(root / "replaced"), revision)
                baseline = {p.name: p.read_bytes() for p in (root / "baseline").iterdir()}
                self.assertEqual(
                    {p.name: p.read_bytes() for p in (root / "replaced").iterdir()}, baseline
                )
                manifest = json.loads(baseline["source-manifest.json"])
                self.assertEqual(
                    manifest, {n: hashlib.sha256(b).hexdigest() for n, b in original.items()}
                )
                self.assertEqual(
                    json.loads(baseline["provenance.json"])["source_revision"], revision
                )
                with tarfile.open(root / "replaced/aethron-0.2.0-source.tar.gz") as archive:
                    for name, data in original.items():
                        with archive.extractfile("aethron-0.2.0/" + name) as member:
                            self.assertEqual(member.read(), data)
                with zipfile.ZipFile(root / "replaced/aethron.pyz") as archive:
                    self.assertEqual(
                        archive.read("aethron/models/rules.json"),
                        original["aethron/models/rules.json"],
                    )
                # Reading releases must not remove the caller's replacement refs.
                self.assertEqual(git("replace", "--list").decode(), old)


if __name__ == "__main__":
    unittest.main()
