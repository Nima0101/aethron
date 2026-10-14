"""Missing committed release inputs must fail before reserving artifact output."""

import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import release


class ReleaseRequiredInputs(unittest.TestCase):
    def test_missing_committed_inputs_allow_corrected_source_retry(self):
        required = {
            "LICENSE": b"synthetic license\n",
            "NOTICE": b"synthetic notice\n",
            "aethron/models/rules.json": b'{"synthetic":true}\n',
        }
        # Similar names, directory descendants and ignored checkout copies
        # cannot supply the exact committed bytes used by the release builder.
        for missing in required:
            for substitute in ("absent", "case", "directory", "ignored"):
                with self.subTest(missing=missing, substitute=substitute):
                    with tempfile.TemporaryDirectory() as directory:
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
                        blobs = {n: data for n, data in required.items() if n != missing}
                        if substitute == "case":
                            blobs[missing.swapcase()] = required[missing]
                        elif substitute == "directory":
                            blobs[missing + "/placeholder"] = b"not a release input\n"
                        elif substitute == "ignored":
                            blobs[".gitignore"] = ("/" + missing + "\n").encode()
                        for name, data in blobs.items():
                            path = source / name
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(data)
                        git("add", ".")
                        git("commit", "--quiet", "-m", "incomplete synthetic source")
                        if substitute == "ignored":
                            path = source / missing
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(required[missing])
                        original = release.committed_blobs("HEAD", root=source)
                        self.assertEqual(git("status", "--porcelain"), b"")
                        destination = root / "new-parent" / "release"
                        with patch.object(release, "ROOT", source):
                            try:
                                release.build(destination)
                            except (KeyError, SystemExit) as error:
                                rejection = error
                            else:
                                self.fail("incomplete source produced release artifacts")
                        self.assertFalse(destination.parent.exists())
                        self.assertIsInstance(rejection, SystemExit)
                        self.assertEqual(
                            str(rejection), "release requires committed release inputs"
                        )
                        self.assertEqual(release.committed_blobs("HEAD", root=source), original)
                        self.assertEqual(git("status", "--porcelain"), b"")

                        # Correct only the disposable fixture, commit it, and
                        # reuse the original destination without cleanup.
                        if substitute == "directory":
                            git("rm", "-r", "--quiet", "--", missing)
                        elif substitute == "case":
                            git("rm", "--quiet", "--", missing.swapcase())
                        path = source / missing
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(required[missing])
                        git("add", "-f", "--", missing)
                        git("commit", "--quiet", "-m", "complete synthetic source")
                        revision = git("rev-parse", "HEAD").decode()
                        with patch.object(release, "ROOT", source):
                            self.assertEqual(release.build(destination), revision)
                            release.build(root / "repeat")
                        self.assertEqual(
                            {p.name: p.read_bytes() for p in destination.iterdir()},
                            {p.name: p.read_bytes() for p in (root / "repeat").iterdir()},
                        )
                        with zipfile.ZipFile(destination / "aethron.pyz") as archive:
                            for name, data in required.items():
                                self.assertEqual(archive.read(name), data)
                        provenance = json.loads((destination / "provenance.json").read_bytes())
                        self.assertEqual(provenance["source_revision"], revision)
                        self.assertEqual(git("status", "--porcelain"), b"")


if __name__ == "__main__":
    unittest.main()
