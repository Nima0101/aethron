"""A stale filesystem monitor must not certify a clean release checkout."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release, reproduce


class ReleaseFsmonitor(unittest.TestCase):
    def check_admission(self, validator):
        for changed in (False, True):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
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

                name = "H spaced café.txt"
                blobs = {
                    "LICENSE": b"synthetic license\n",
                    "NOTICE": b"synthetic notice\n",
                    "aethron/models/rules.json": b"{}\n",
                    name: b"committed source\n",
                }
                for filename, data in blobs.items():
                    path = source / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                git("init", "--quiet")
                git("add", ".")
                git("commit", "--quiet", "-m", "synthetic source")
                revision = git("rev-parse", "HEAD").decode().strip()
                # A synthetic protocol-v2 monitor reports no changes even
                # after an edit, reproducing an incomplete notification list.
                # This hook/config exists only in this disposable repository.
                hook = source / ".git" / "fixture-monitor"
                hook.write_bytes(b'#!/bin/sh\nprintf "fixture-token\\0"\n')
                hook.chmod(0o755)
                git("config", "core.fsmonitor", str(hook))
                git("config", "core.fsmonitorHookVersion", "2")
                git("update-index", "--fsmonitor")
                git("status", "--porcelain")
                git("update-index", "--fsmonitor-valid", "--", name)
                if changed:
                    (source / name).write_bytes(b"hidden modification\n")
                self.assertEqual(git("status", "--porcelain"), b"")
                self.assertIn(b"H " + name.encode() + b"\0", git("ls-files", "-v", "-z"))
                flags = git("ls-files", "-v", "-f", "-z")
                self.assertIn(b"h " + name.encode() + b"\0", flags)
                config = (source / ".git" / "config").read_bytes()
                index = (source / ".git" / "index").read_bytes()
                destination = root / "new-parent" / "output"

                with patch.object(release, "ROOT", source):
                    if validator == "release":
                        with self.assertRaisesRegex(SystemExit, "observable source index"):
                            release.build(destination)
                    else:
                        with self.assertRaisesRegex(ValueError, "reproduction_source_changed"):
                            reproduce.validate_source(source, revision)
                self.assertFalse(destination.parent.exists())
                self.assertEqual(git("ls-files", "-v", "-f", "-z"), flags)
                self.assertEqual((source / ".git" / "index").read_bytes(), index)
                self.assertEqual((source / ".git" / "config").read_bytes(), config)
                self.assertEqual(
                    (source / name).read_bytes(),
                    b"hidden modification\n" if changed else blobs[name],
                )

                # Disable the fixture monitor explicitly. The ordinary dirty
                # source gate still applies; restoring bytes permits retry.
                git("config", "core.fsmonitor", "false")
                with patch.object(release, "ROOT", source):
                    if changed:
                        with self.assertRaisesRegex(SystemExit, "clean committed source"):
                            release.build(destination)
                        with self.assertRaisesRegex(ValueError, "reproduction_source_changed"):
                            reproduce.validate_source(source, revision)
                        self.assertFalse(destination.parent.exists())
                    (source / name).write_bytes(blobs[name])
                    reproduce.validate_source(source, revision)
                    release.build(destination)
                    release.build(root / "repeat")
                self.assertEqual(
                    {p.name: p.read_bytes() for p in destination.iterdir()},
                    {p.name: p.read_bytes() for p in (root / "repeat").iterdir()},
                )
                reproduce.validate_source(source, revision)

    def test_release_rejects_monitor_cached_source(self):
        self.check_admission("release")

    def test_reproduction_rejects_monitor_cached_source(self):
        self.check_admission("reproduction")


if __name__ == "__main__":
    unittest.main()
