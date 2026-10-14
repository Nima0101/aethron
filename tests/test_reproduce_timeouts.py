"""A stalled reproduction Git child retains evidence and cannot report success."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import git_context, reproduce


class ReproductionTimeouts(unittest.TestCase):
    def test_each_git_stage_stops_and_retains_the_failed_workspace(self):
        commands = ["clone", "rev-parse", "ls-files", "rev-parse", "status"]
        responses = [None, b"a" * 40 + b"\n", b"H source.txt\0", b"a" * 40 + b"\n"]
        for stage, command in enumerate(commands):
            with self.subTest(stage=stage, command=command):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    calls = []
                    error = subprocess.TimeoutExpired(
                        ["git", command], 30, output=b"partial output", stderr=b"partial error"
                    )

                    def child(args, calls=calls, stage=stage, error=error, **kwargs):
                        index = len(calls)
                        calls.append((args, kwargs))
                        self.assertEqual(args[0], "git", "a later consumer was started")
                        if index == 0:
                            clone = Path(args[-1])
                            clone.mkdir()
                            (clone / "partial.txt").write_bytes(b"retained evidence")
                        if index == stage:
                            raise error
                        return responses[index]

                    with (
                        patch.object(tempfile, "tempdir", str(root)),
                        patch.object(reproduce.subprocess, "run", side_effect=child),
                        patch.object(git_context, "git_output", side_effect=child),
                        contextlib.redirect_stdout(io.StringIO()) as output,
                        contextlib.redirect_stderr(io.StringIO()) as diagnostics,
                    ):
                        with self.assertRaises(subprocess.TimeoutExpired) as caught:
                            reproduce.run()
                    self.assertIs(caught.exception, error)
                    self.assertEqual(caught.exception.output, b"partial output")
                    self.assertEqual(caught.exception.stderr, b"partial error")
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(len(calls), stage + 1)
                    workspaces = list(root.iterdir())
                    self.assertEqual(len(workspaces), 1)
                    workspace = workspaces[0]
                    self.assertIn(str(workspace), diagnostics.getvalue())
                    self.assertEqual(
                        (workspace / "source/partial.txt").read_bytes(), b"retained evidence"
                    )
                    self.assertEqual(sorted(p.name for p in workspace.iterdir()), ["source"])
                    for index, (args, kwargs) in enumerate(calls):
                        self.assertEqual(args[1 if index == 0 else 2], commands[index])
                        self.assertEqual(kwargs.get("timeout"), 180 if index == 0 else 30)

    def test_real_stalled_clone_child_is_reaped_and_workspace_is_retained(self):
        run = subprocess.run
        popen = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            process = popen(*args, **kwargs)
            children.append(process)
            return process

        def stalled(args, **kwargs):
            self.assertEqual(args[:2], ["git", "clone"])
            return run(
                [sys.executable, "-c", "import time; time.sleep(1)"],
                cwd=kwargs["cwd"],
                capture_output=True,
                timeout=kwargs.get("timeout", 2),
                check=True,
            )

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(tempfile, "tempdir", directory),
                patch.object(reproduce, "GIT_CLONE_TIMEOUT_SECONDS", 0.1, create=True),
                patch.object(subprocess, "run", side_effect=stalled),
                patch.object(subprocess, "Popen", side_effect=spawn),
                contextlib.redirect_stdout(io.StringIO()) as output,
                contextlib.redirect_stderr(io.StringIO()) as diagnostics,
            ):
                with self.assertRaises(subprocess.TimeoutExpired):
                    reproduce.run()
            workspaces = list(Path(directory).iterdir())
            self.assertEqual(len(workspaces), 1)
            self.assertIn(str(workspaces[0]), diagnostics.getvalue())
            self.assertEqual(output.getvalue(), "")
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
        self.assertIsNotNone(children[0].poll())


if __name__ == "__main__":
    unittest.main()
