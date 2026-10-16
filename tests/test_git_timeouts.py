"""Developer Git timeout behavior with mocks and one owned synthetic child."""

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import git_context, public_links, verify


class GitTimeouts(unittest.TestCase):
    def test_root_and_inventory_each_have_a_finite_budget(self):
        with patch.object(verify, "git_output", side_effect=[b"true\n\n", b"README.md\0"]) as git:
            self.assertEqual(verify.tracked_files(), {"README.md"})
        self.assertEqual(git.call_count, 2)
        for call in git.call_args_list:
            self.assertEqual(call.kwargs.get("timeout"), 30)

    def test_all_public_tree_git_reads_have_a_finite_budget(self):
        with patch.object(
            public_links,
            "git_output",
            side_effect=[b"tree\n", b"100644 blob blob\tREADME.md\0", b"synthetic"],
        ) as git:
            self.assertEqual(public_links.check(Path("."), "HEAD"), {"tree": "tree", "missing": []})
        self.assertEqual(git.call_count, 3)
        for call in git.call_args_list:
            self.assertEqual(call.kwargs.get("timeout"), 30)

    def test_root_timeout_prevents_product_children_and_reads(self):
        error = subprocess.TimeoutExpired(["git", "rev-parse"], 30)
        with (
            patch.object(verify, "git_output", side_effect=error),
            patch.object(verify.subprocess, "run") as child,
            patch.object(verify, "local_bytes") as read,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                verify.run()
            self.assertIs(caught.exception, error)
            child.assert_not_called()
            read.assert_not_called()
            self.assertEqual(output.getvalue(), "")

    def test_later_git_timeout_never_returns_partial_success(self):
        error = subprocess.TimeoutExpired(["git"], 30, output=b"partial")
        with patch.object(verify, "git_output", side_effect=[b"true\n\n", error]):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                verify.tracked_files()
            self.assertIs(caught.exception, error)
        responses = [b"tree\n", b"100644 blob blob\tREADME.md\0"]
        for stage in range(3):
            with (
                self.subTest(stage=stage),
                patch.object(public_links, "git_output", side_effect=responses[:stage] + [error]),
            ):
                with self.assertRaises(subprocess.TimeoutExpired) as caught:
                    public_links.check(Path("."), "HEAD")
                self.assertIs(caught.exception, error)

    def test_public_cli_timeout_is_fixed_diagnostic_without_partial_output(self):
        error = subprocess.TimeoutExpired(["synthetic-private-path"], 30, output=b"private")
        with (
            patch.object(sys, "argv", ["public_links.py", "HEAD"]),
            patch.object(public_links, "check", side_effect=error),
            contextlib.redirect_stdout(io.StringIO()) as output,
            contextlib.redirect_stderr(io.StringIO()) as diagnostic,
        ):
            with self.assertRaises(SystemExit) as caught:
                public_links.main()
            self.assertEqual(caught.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(diagnostic.getvalue(), "invalid_public_tree\n")

    def test_timeout_reaps_owned_synthetic_direct_child(self):
        real_capture = git_context.git_output
        real_popen = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        def substitute_child(args, **kwargs):
            self.assertEqual(args[0], "git")
            return real_capture(
                [sys.executable, "-c", "import time; print('true\\n', flush=True); time.sleep(1)"],
                timeout=kwargs.get("timeout", 2),
                cwd=Path.cwd(),
            )

        with (
            patch.object(verify, "GIT_COMMAND_TIMEOUT_SECONDS", 0.1, create=True),
            patch.object(verify, "git_output", side_effect=substitute_child),
            patch.object(subprocess, "Popen", side_effect=spawn),
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                verify.require_worktree_root()
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
        self.assertIsNotNone(children[0].poll())
