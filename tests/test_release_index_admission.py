"""A clean status cannot certify source hidden by Git index flags."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release


class ReleaseIndexAdmission(unittest.TestCase):
    def test_hidden_source_rejects_before_output_and_preserves_index(self):
        for flags in (
            ("--assume-unchanged",),
            ("--skip-worktree",),
            ("--assume-unchanged", "--skip-worktree"),
        ):
            for changed in (False, True):
                with self.subTest(flags=flags, changed=changed):
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
                            )

                        blobs = {
                            "LICENSE": b"synthetic license\n",
                            "NOTICE": b"synthetic notice\n",
                            "aethron/models/rules.json": b"{}\n",
                            "H spaced café.txt": b"committed source\n",
                        }
                        for name, data in blobs.items():
                            path = source / name
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(data)
                        git("init", "--quiet")
                        git("add", ".")
                        git("commit", "--quiet", "-m", "synthetic source")
                        name = "H spaced café.txt"
                        for flag in flags:
                            git("update-index", flag, "--", name)
                        if changed:
                            (source / name).write_bytes(b"hidden local modification\n")
                        self.assertEqual(git("status", "--porcelain"), b"")
                        index = git("ls-files", "-v", "-z")
                        destination = root / "new-parent" / "output"
                        with patch.object(release, "ROOT", source):
                            with self.assertRaisesRegex(
                                SystemExit, "release requires observable source index"
                            ):
                                release.build(destination)
                        self.assertFalse(destination.parent.exists())
                        self.assertEqual(git("ls-files", "-v", "-z"), index)
                        self.assertEqual(
                            (source / name).read_bytes(),
                            b"hidden local modification\n" if changed else blobs[name],
                        )

                        # Clear flags only in the disposable fixture. Exposed
                        # edits must still fail the ordinary clean-source gate.
                        for flag in flags:
                            git("update-index", flag.replace("--", "--no-", 1), "--", name)
                        with patch.object(release, "ROOT", source):
                            if changed:
                                with self.assertRaisesRegex(SystemExit, "clean committed source"):
                                    release.build(destination)
                                self.assertFalse(destination.parent.exists())
                            (source / name).write_bytes(blobs[name])
                            release.build(destination)
                            release.build(root / "repeat")
                        self.assertEqual(
                            {p.name: p.read_bytes() for p in destination.iterdir()},
                            {p.name: p.read_bytes() for p in (root / "repeat").iterdir()},
                        )
                        self.assertEqual(git("status", "--porcelain"), b"")


if __name__ == "__main__":
    unittest.main()
