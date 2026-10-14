"""Release metadata capture must reject excess bytes before creating artifacts."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import git_context, release


class ReleaseOutputLimit(unittest.TestCase):
    def test_each_metadata_stage_rejects_excess_and_reaps_child_before_output(self):
        responses = [b"H LICENSE\0", b"a" * 40 + b"\n", b"", b""]
        commands = ["ls-files", "rev-parse", "status", "ls-tree"]
        popen = subprocess.Popen
        for stage in range(len(responses)):
            with self.subTest(stage=commands[stage]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "LICENSE").write_bytes(b"retained source")
                destination = root / "new-parent" / "release"
                children = []

                def spawn(args, stage=stage, children=children, **kwargs):
                    index = len(children)
                    self.assertLessEqual(index, stage, "later Git stage started")
                    self.assertEqual(args[:3], ["git", "--no-replace-objects", commands[index]])
                    payload = b"x" * 262144 if index == stage else responses[index]
                    # Keep the child command small even for the excess payload.
                    code = (
                        "import os; os.write(1, b'x' * 262144)"
                        if index == stage
                        else f"import os; os.write(1, {payload!r})"
                    )
                    child = popen([sys.executable, "-c", code], **kwargs)
                    children.append(child)
                    return child

                with (
                    patch.object(release, "ROOT", root),
                    patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", 128),
                    patch.object(subprocess, "Popen", side_effect=spawn),
                    patch.object(release, "_write_artifacts") as write,
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    try:
                        release.build(destination)
                    except (ValueError, SystemExit, AssertionError) as error:
                        caught = error
                    else:
                        caught = None
                self.assertIs(type(caught), ValueError)
                self.assertEqual(str(caught), "git_output_limit")
                write.assert_not_called()
                self.assertEqual(output.getvalue(), "")
                self.assertFalse(destination.parent.exists())
                self.assertEqual((root / "LICENSE").read_bytes(), b"retained source")
                self.assertEqual(len(children), stage + 1)
                for child in children:
                    self.assertIsNotNone(child.poll())
                    self.assertTrue(child.stdout.closed)

    def test_real_git_exact_metadata_limit_preserves_large_blobs_and_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()

            def git(*args):
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
                        "core.hooksPath=" + str(root / "no-hooks"),
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
                "space café.bin": bytes(range(256)) * 64,
            }
            for name, data in blobs.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            git("init", "--quiet")
            git("add", ".")
            git("commit", "--quiet", "-m", "synthetic source")
            sizes = [
                len(git(*args))
                for args in (
                    ("ls-files", "-v", "-f", "-z"),
                    ("rev-parse", "HEAD"),
                    ("status", "--porcelain", "--untracked-files=normal"),
                    ("ls-tree", "-r", "-t", "-z", "--full-tree", "HEAD"),
                )
            ]
            limit = max(sizes)
            self.assertGreater(len(blobs["space café.bin"]), limit)
            destination = root / "new-parent" / "release"
            with patch.object(release, "ROOT", source):
                with patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", limit - 1):
                    with self.assertRaisesRegex(ValueError, "^git_output_limit$"):
                        release.build(destination)
                self.assertFalse(destination.parent.exists())
                with patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", limit):
                    release.build(destination)
                    self.assertEqual(release.committed_blobs("HEAD"), blobs)
                release.build(root / "uncapped-baseline")
            self.assertEqual(
                {p.name: p.read_bytes() for p in destination.iterdir()},
                {p.name: p.read_bytes() for p in (root / "uncapped-baseline").iterdir()},
            )
            self.assertEqual(git("status", "--porcelain"), b"")


if __name__ == "__main__":
    unittest.main()
