"""Every completed reproduction child must leave the original source observable."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import reproduce


class ReproductionStageSource(unittest.TestCase):
    def test_changed_source_stops_before_next_child_and_retains_evidence(self):
        # Real Git clones/index/status; only expensive Python checks are replaced.
        # Cover verification, evaluation, three quickstarts, refusal, and both builds.
        real_run = subprocess.run
        for stage in range(8):
            for mutation in (
                "modified",
                "untracked",
                "assume-unchanged",
                "skip-worktree",
                "revision",
            ):
                with self.subTest(stage=stage, mutation=mutation):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        source = root / "original"
                        source.mkdir()

                        def git(*args, cwd=source, root=root):
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
                        (source / "aethron").mkdir()
                        (source / "aethron/source.txt").write_bytes(b"original source\n")
                        git("add", ".")
                        git("commit", "--quiet", "-m", "synthetic source")
                        calls, clones = [], []

                        def child(
                            args,
                            calls=calls,
                            clones=clones,
                            stage=stage,
                            mutation=mutation,
                            git=git,
                            **kwargs,
                        ):
                            if args[0] != sys.executable:
                                result = real_run(args, **kwargs)
                                if args[:2] == ["git", "clone"]:
                                    clones.append(Path(args[-1]))
                                return result
                            calls.append(args)
                            clone = clones[0]
                            path = clone / "aethron/source.txt"
                            if len(calls) > stage + 1:
                                # A later child could restore bytes and hide an earlier
                                # stage's change. It must never receive control here.
                                path.write_bytes(b"original source\n")
                                raise AssertionError("next child ran against changed source")
                            if len(calls) == stage + 1:
                                if mutation == "revision":
                                    git(
                                        "commit",
                                        "--quiet",
                                        "--allow-empty",
                                        "-m",
                                        "changed",
                                        cwd=clone,
                                    )
                                elif mutation == "untracked":
                                    (clone / "extra.txt").write_bytes(b"unexpected source\n")
                                else:
                                    if mutation != "modified":
                                        git(
                                            "update-index",
                                            "--" + mutation,
                                            "aethron/source.txt",
                                            cwd=clone,
                                        )
                                    path.write_bytes(b"changed source\n")
                            if (
                                args[1:2] == ["scripts/release.py"]
                                and Path(args[-1]).name == "refused"
                            ):
                                return subprocess.CompletedProcess(
                                    args, 1, stderr=b"release requires clean committed source"
                                )
                            return subprocess.CompletedProcess(args, 0)

                        workspace = reproduce.reproduction_workspace
                        output, diagnostics = io.StringIO(), io.StringIO()
                        error = None
                        with (
                            patch.object(reproduce, "ROOT", source),
                            patch.object(reproduce.subprocess, "run", side_effect=child),
                            patch.object(
                                reproduce,
                                "reproduction_workspace",
                                side_effect=lambda workspace=workspace, root=root: workspace(
                                    dir=root
                                ),
                            ),
                            contextlib.redirect_stdout(output),
                            contextlib.redirect_stderr(diagnostics),
                        ):
                            try:
                                reproduce.run()
                            except Exception as caught:
                                error = caught
                        self.assertIsInstance(error, ValueError)
                        self.assertEqual(str(error), "reproduction_source_changed")
                        self.assertEqual(len(calls), stage + 1)
                        self.assertEqual(output.getvalue(), "")
                        clone = clones[0]
                        self.assertTrue(clone.is_dir())
                        self.assertIn(str(clone.parent), diagnostics.getvalue())
                        if mutation in ("modified", "assume-unchanged", "skip-worktree"):
                            self.assertEqual(
                                (clone / "aethron/source.txt").read_bytes(), b"changed source\n"
                            )


if __name__ == "__main__":
    unittest.main()
