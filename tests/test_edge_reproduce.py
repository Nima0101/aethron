"""Exercise source/workspace ownership with real Git and synthetic package/test children."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_reproduce


class EdgeReproductionSource(unittest.TestCase):
    def test_child_source_changes_reject_before_the_next_stage(self):
        mutations = ("modified", "untracked", "assume-unchanged", "skip-worktree", "revision")
        cases = [
            (stage, mutation)
            for stage in range(4)
            for mutation in mutations
            # The initial clone establishes the revision used by every later stage.
            if stage != 0 or mutation != "revision"
        ]
        cases.extend(((None, None), (None, "ignored")))
        real_run = subprocess.run
        for changed_stage, mutation in cases:
            with self.subTest(stage=changed_stage, mutation=mutation):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)

                    def git(*args, cwd=root, root=root):
                        return real_run(
                            [
                                "git",
                                "-c",
                                "user.name=Reproduction Fixture",
                                "-c",
                                "user.email=fixture@example.invalid",
                                "-c",
                                "commit.gpgsign=false",
                                "-c",
                                "core.hooksPath=" + str(root / "no-hooks"),
                                *args,
                            ],
                            cwd=cwd,
                            check=True,
                            capture_output=True,
                            timeout=5,
                        )

                    git("init", "--quiet")
                    (root / "source.txt").write_bytes(b"original source\n")
                    (root / ".gitignore").write_bytes(b"build/\n")
                    git("add", "source.txt", ".gitignore")
                    git("commit", "--quiet", "-m", "synthetic source")
                    calls, clones = [], []
                    output, diagnostics = io.StringIO(), io.StringIO()

                    def child(
                        args,
                        calls=calls,
                        clones=clones,
                        mutation=mutation,
                        changed_stage=changed_stage,
                        git=git,
                        **kwargs,
                    ):
                        # Validators use real Git; only package/test child results are fake.
                        if args[0] == "git" and args[1] != "clone":
                            return real_run(args, **kwargs)
                        stage = len(calls)
                        calls.append(args)
                        if stage == 0:
                            real_run(args, **kwargs)
                            clones.append(Path(args[-1]))
                        clone = clones[0]
                        if mutation == "ignored":
                            (clone / "build").mkdir(exist_ok=True)
                            (clone / "build/output.txt").write_bytes(b"build evidence\n")
                        elif stage == changed_stage:
                            if mutation == "revision":
                                git(
                                    "commit",
                                    "--quiet",
                                    "--allow-empty",
                                    "-m",
                                    "new revision",
                                    cwd=clone,
                                )
                            elif mutation == "untracked":
                                (clone / "extra.txt").write_bytes(b"new source\n")
                                git("config", "status.showUntrackedFiles", "no", cwd=clone)
                            else:
                                if mutation in ("assume-unchanged", "skip-worktree"):
                                    git("update-index", "--" + mutation, "source.txt", cwd=clone)
                                (clone / "source.txt").write_bytes(b"changed source\n")
                        return subprocess.CompletedProcess(args, 0)

                    with (
                        patch.object(edge_reproduce, "ROOT", root),
                        patch.object(edge_reproduce.subprocess, "run", side_effect=child),
                        contextlib.redirect_stdout(output),
                        contextlib.redirect_stderr(diagnostics),
                    ):
                        if changed_stage is None:
                            edge_reproduce.run(root / "wheelhouse")
                        else:
                            with self.assertRaisesRegex(
                                ValueError, "^reproduction_source_changed$"
                            ):
                                edge_reproduce.run(root / "wheelhouse")

                    clone = clones[0]
                    if changed_stage is None:
                        self.assertEqual(len(calls), 4)
                        self.assertIn("PASS:", output.getvalue())
                        self.assertFalse(clone.parent.exists())
                    else:
                        self.assertEqual(len(calls), changed_stage + 1)
                        self.assertEqual(output.getvalue(), "")
                        self.assertTrue(clone.is_dir())
                        self.assertIn(str(clone.parent), diagnostics.getvalue())
                        if mutation in ("modified", "assume-unchanged", "skip-worktree"):
                            self.assertEqual(
                                (clone / "source.txt").read_bytes(), b"changed source\n"
                            )


class EdgeReproductionWorkspace(unittest.TestCase):
    def test_failure_retains_workspace_and_success_cleans_it(self):
        failures = (
            subprocess.CalledProcessError(7, ["synthetic-check"]),
            SystemExit(9),
            KeyboardInterrupt(),
        )
        cases = [(stage, error) for stage in range(4) for error in failures]
        cases.append((None, None))
        for failed_stage, failure in cases:
            with self.subTest(stage=failed_stage, failure=failure):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    output, diagnostics = io.StringIO(), io.StringIO()
                    calls = []
                    clones = []

                    def child(
                        args,
                        calls=calls,
                        clones=clones,
                        failed_stage=failed_stage,
                        failure=failure,
                        **kwargs,
                    ):
                        stage = len(calls)
                        calls.append(args)
                        self.assertTrue(kwargs["check"])
                        if stage == 0:
                            clone = Path(args[-1])
                            clone.mkdir()
                            clones.append(clone)
                        clone = clones[0]
                        (clone / "partial.bin").write_bytes(b"partial\x00evidence")
                        if stage == failed_stage:
                            raise failure
                        return subprocess.CompletedProcess(args, 0)

                    with (
                        patch.object(edge_reproduce, "ROOT", root),
                        patch.object(edge_reproduce.subprocess, "run", side_effect=child),
                        patch.object(
                            edge_reproduce.subprocess, "check_output", return_value="a" * 40
                        ),
                        patch.object(edge_reproduce, "validate_source"),
                        contextlib.redirect_stdout(output),
                        contextlib.redirect_stderr(diagnostics),
                    ):
                        if failure is None:
                            edge_reproduce.run(root / "wheelhouse")
                        else:
                            with self.assertRaises(type(failure)) as caught:
                                edge_reproduce.run(root / "wheelhouse")
                            self.assertIs(caught.exception, failure)

                    workspace = clones[0].parent
                    self.assertEqual(workspace.parent, root / "build/ecosystem-phase1")
                    self.assertTrue(workspace.name.startswith("clean-edge-"))
                    if failure is None:
                        self.assertEqual(len(calls), 4)
                        self.assertFalse(workspace.exists())
                        self.assertIn("PASS:", output.getvalue())
                        self.assertEqual(diagnostics.getvalue(), "")
                    else:
                        self.assertEqual(len(calls), failed_stage + 1)
                        self.assertTrue(workspace.is_dir(), "failed run erased its evidence")
                        self.assertEqual(
                            (clones[0] / "partial.bin").read_bytes(), b"partial\x00evidence"
                        )
                        self.assertIn(str(workspace), diagnostics.getvalue())
                        self.assertEqual(output.getvalue(), "")
