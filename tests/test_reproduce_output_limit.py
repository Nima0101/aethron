"""Reproduction metadata reads reuse the bounded developer Git reader."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import git_context, reproduce


class ReproductionOutputLimit(unittest.TestCase):
    def test_exact_limit_binary_and_revision_text(self):
        with patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", 32):
            self.assertEqual(
                reproduce._git_output(
                    [sys.executable, "-c", "import os; os.write(1, bytes(range(32)))"],
                    cwd=Path.cwd(),
                ),
                bytes(range(32)),
            )
            for newline in (None, "\n", "\r\n"):
                with self.subTest(newline=newline):
                    # Model Git's exact bytes even when the child's text stdout
                    # would expand LF to CRLF (33 bytes, beyond this 32-byte cap).
                    command = [
                        sys.executable,
                        "-c",
                        f"import sys; sys.stdout.reconfigure(newline={newline!r}); "
                        "sys.stdout.buffer.write(b'a' * 31 + b'\\n')",
                    ]
                    self.assertEqual(
                        reproduce._git_output(command, cwd=Path.cwd(), text=True),
                        "a" * 31 + "\n",
                    )
                    with patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", 31):
                        with self.assertRaisesRegex(ValueError, "^git_output_limit$"):
                            reproduce._git_output(command, cwd=Path.cwd(), text=True)

    def test_oversized_read_rejects_without_prefix_and_reaps_child(self):
        popen = subprocess.Popen
        for text in (False, True):
            children = []

            def spawn(*args, children=children, **kwargs):
                child = popen(*args, **kwargs)
                children.append(child)
                return child

            with (
                self.subTest(text=text),
                patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", 32),
                patch.object(subprocess, "Popen", side_effect=spawn),
            ):
                with self.assertRaisesRegex(ValueError, "^git_output_limit$"):
                    reproduce._git_output(
                        [sys.executable, "-c", "import os; os.write(1, b'x' * 262144)"],
                        cwd=Path.cwd(),
                        text=text,
                    )
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].poll())
                self.assertTrue(children[0].stdout.closed)

    def test_each_metadata_stage_retains_failure_without_starting_verification(self):
        responses = [b"a" * 40 + b"\n", b"H source.txt\0", b"a" * 40 + b"\n", b""]
        popen = subprocess.Popen
        for stage in range(len(responses)):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                children = []

                def clone(args, cwd, **kwargs):
                    self.assertEqual(args[:2], ["git", "clone"])
                    source = Path(args[-1])
                    source.mkdir()
                    (source / "source.txt").write_bytes(b"retained evidence")
                    return subprocess.CompletedProcess(args, 0)

                def metadata(args, stage=stage, children=children, **kwargs):
                    index = len(children)
                    if index > stage:
                        raise ValueError("later_stage_started")
                    self.assertEqual(args[:2], ["git", "--no-replace-objects"])
                    payload = b"x" * 65 if index == stage else responses[index]
                    child = popen(
                        [sys.executable, "-c", f"import os; os.write(1, {payload!r})"],
                        **kwargs,
                    )
                    children.append(child)
                    return child

                with (
                    patch.object(tempfile, "tempdir", directory),
                    patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", 64),
                    patch.object(reproduce, "call", side_effect=clone) as run,
                    patch.object(subprocess, "Popen", side_effect=metadata),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                    contextlib.redirect_stderr(io.StringIO()) as diagnostic,
                ):
                    with self.assertRaisesRegex(ValueError, "^git_output_limit$"):
                        reproduce.run()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(output.getvalue(), "")
                workspaces = list(Path(directory).iterdir())
                self.assertEqual(len(workspaces), 1)
                workspace = workspaces[0]
                self.assertIn(str(workspace), diagnostic.getvalue())
                self.assertEqual(
                    (workspace / "source/source.txt").read_bytes(), b"retained evidence"
                )
                self.assertEqual(len(children), stage + 1)
                for child in children:
                    self.assertIsNotNone(child.poll())
                    self.assertTrue(child.stdout.closed)


if __name__ == "__main__":
    unittest.main()
