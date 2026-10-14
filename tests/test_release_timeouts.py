"""Release Git stalls must stop before any artifact is created."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release


class ReleaseTimeouts(unittest.TestCase):
    def test_every_git_stage_has_a_budget_and_preserves_timeout_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "LICENSE").write_bytes(b"fixture\n")
            oid = b"a" * 40
            responses = [
                b"H LICENSE\0",
                "b" * 40 + "\n",
                b"",
                b"100644 blob " + oid + b"\tLICENSE\0",
            ]
            commands = ["ls-files", "rev-parse", "status", "ls-tree", "cat-file"]
            for stage, command in enumerate(commands):
                with self.subTest(stage=command):
                    destination = root / ("release-" + command)
                    error = subprocess.TimeoutExpired(["git", command], 30, output=b"partial")
                    with (
                        patch.object(release, "ROOT", source),
                        patch.object(
                            release.subprocess,
                            "check_output",
                            side_effect=responses[:stage] + [error],
                        ) as read,
                        contextlib.redirect_stdout(io.StringIO()) as output,
                    ):
                        with self.assertRaises(subprocess.TimeoutExpired) as caught:
                            release.build(destination)
                    self.assertIs(caught.exception, error)
                    self.assertEqual(caught.exception.output, b"partial")
                    self.assertFalse(destination.exists())
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(read.call_count, stage + 1)
                    for index, call in enumerate(read.call_args_list):
                        self.assertEqual(
                            call.args[0][:3], ["git", "--no-replace-objects", commands[index]]
                        )
                        self.assertEqual(call.kwargs.get("timeout"), 30)
                    self.assertEqual((source / "LICENSE").read_bytes(), b"fixture\n")

    def test_real_stalled_child_is_reaped_without_artifacts(self):
        capture = subprocess.check_output
        popen = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            child = popen(*args, **kwargs)
            children.append(child)
            return child

        def substitute(args, **kwargs):
            self.assertEqual(args[:3], ["git", "--no-replace-objects", "ls-files"])
            return capture(
                [sys.executable, "-c", "import time; time.sleep(1)"],
                cwd=kwargs["cwd"],
                timeout=kwargs.get("timeout", 2),
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(release, "ROOT", root),
                patch.object(release, "GIT_COMMAND_TIMEOUT_SECONDS", 0.1, create=True),
                patch.object(subprocess, "check_output", side_effect=substitute),
                patch.object(subprocess, "Popen", side_effect=spawn),
            ):
                with self.assertRaises(subprocess.TimeoutExpired):
                    release.build(root / "release")
            self.assertFalse((root / "release").exists())
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
        self.assertIsNotNone(children[0].poll())


if __name__ == "__main__":
    unittest.main()
