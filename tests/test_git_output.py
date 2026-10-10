"""Bounded developer-tool capture, using small owned synthetic producers only."""

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import git_context, public_links, verify


class GitOutput(unittest.TestCase):
    def capture(self, source, limit=32, timeout=5):
        operation = git_context.git_output
        with patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", limit, create=True):
            return operation([sys.executable, "-c", source], cwd=Path.cwd(), timeout=timeout)

    def test_reads_request_only_remaining_capacity_plus_one(self):
        real_popen = subprocess.Popen
        requests = []

        def spawn(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            read = child.stdout.read

            def bounded_read(size):
                requests.append(size)
                return read(size)

            child.stdout.read = bounded_read
            return child

        with patch.object(subprocess, "Popen", side_effect=spawn):
            self.assertEqual(self.capture("import os; os.write(1, b'x' * 32)"), b"x" * 32)
        self.assertTrue(requests)
        self.assertLessEqual(max(requests), 33)
        self.assertEqual(requests[-1], 1)

    def test_exact_limit_and_binary_output_survive(self):
        self.assertEqual(self.capture("import os; os.write(1, bytes(range(32)))"), bytes(range(32)))
        self.assertEqual(self.capture("pass"), b"")

    def test_one_byte_over_limit_never_returns_a_prefix(self):
        with self.assertRaisesRegex(ValueError, "^git_output_limit$"):
            self.capture("import os; os.write(1, b'x' * 33)")

    def test_large_output_is_rejected_and_direct_child_is_reaped(self):
        real_popen = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        with patch.object(subprocess, "Popen", side_effect=spawn):
            with self.assertRaisesRegex(ValueError, "^git_output_limit$"):
                self.capture("import os; os.write(1, b'x' * 262144)")
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)

    def test_stderr_is_discarded_and_cannot_fill_a_capture_pipe(self):
        with patch.object(subprocess, "Popen", wraps=subprocess.Popen) as spawn:
            self.assertEqual(
                self.capture("import os; os.write(2, b'x' * 262144); os.write(1, b'ok')"), b"ok"
            )
        self.assertEqual(spawn.call_args.kwargs.get("stderr"), subprocess.DEVNULL)

    def test_failure_does_not_attach_partial_output(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.capture("import os; os.write(1, b'private'); raise SystemExit(7)")
        self.assertEqual(caught.exception.returncode, 7)
        self.assertIsNone(caught.exception.output)
        self.assertIsNone(caught.exception.stderr)

    def test_timeout_does_not_attach_partial_output(self):
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            self.capture("import os,time; os.write(1,b'private'); time.sleep(1)", timeout=0.1)
        self.assertIsNone(caught.exception.output)

    def test_public_cli_limit_failure_has_fixed_diagnostic(self):
        with (
            patch.object(sys, "argv", ["public_links.py", "HEAD"]),
            patch.object(public_links, "check", side_effect=ValueError("git_output_limit")),
            contextlib.redirect_stdout(io.StringIO()) as output,
            contextlib.redirect_stderr(io.StringIO()) as diagnostic,
        ):
            with self.assertRaises(SystemExit) as caught:
                public_links.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(diagnostic.getvalue(), "invalid_public_tree\n")

    def test_reader_start_failure_reaps_child_and_closes_pipe(self):
        real_popen = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        with (
            patch.object(subprocess, "Popen", side_effect=spawn),
            patch.object(
                git_context.threading.Thread, "start", side_effect=RuntimeError("no thread")
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "^no thread$"):
                self.capture("import time; time.sleep(1)")
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)

    def test_stdout_eof_does_not_bypass_process_timeout(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.capture("import os,time; os.close(1); time.sleep(1)", timeout=0.1)

    def test_stream_failure_never_returns_success(self):
        real_popen = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            child.stdout.read = lambda size: (_ for _ in ()).throw(OSError("synthetic read error"))
            return child

        with patch.object(subprocess, "Popen", side_effect=spawn):
            with self.assertRaisesRegex(OSError, "^synthetic read error$"):
                self.capture("import time; time.sleep(1)")
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)

    def test_checker_entry_points_reject_excess_before_product_work(self):
        real_popen = subprocess.Popen

        def substitute_git(args, **kwargs):
            self.assertEqual(args[0], "git")
            return real_popen([sys.executable, "-c", "import os; os.write(1, b'x' * 33)"], **kwargs)

        for operation in (verify.run, lambda: public_links.check(Path.cwd(), "HEAD")):
            with (
                self.subTest(operation=operation),
                patch.object(git_context, "GIT_OUTPUT_MAX_BYTES", 32),
                patch.object(subprocess, "Popen", side_effect=substitute_git),
                patch.object(subprocess, "run") as child,
                patch.object(verify, "local_bytes") as read,
            ):
                with self.assertRaisesRegex(ValueError, "^git_output_limit$"):
                    operation()
                child.assert_not_called()
                read.assert_not_called()
