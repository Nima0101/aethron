"""Exercise source/workspace ownership with real Git and synthetic package/test children."""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_reproduce


class EdgeReproductionSource(unittest.TestCase):
    def test_python_children_ignore_inherited_python_home_and_path(self):
        for existing_home in (False, True):
            with self.subTest(existing_home=existing_home):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source = root / "source"
                    source.mkdir()
                    foreign_home = root / "foreign-home"
                    if existing_home:
                        foreign_home.mkdir()
                    foreign_path = root / "foreign-path"
                    foreign_path.mkdir()
                    (foreign_path / "sitecustomize.py").write_text(
                        "raise SystemExit('foreign sitecustomize executed')\n", encoding="utf-8"
                    )
                    scripts = source / "scripts"
                    scripts.mkdir()
                    probe = (
                        "import json, os, sys\n"
                        "from pathlib import Path\n"
                        "assert 'PYTHONHOME' not in os.environ\n"
                        "assert 'PYTHONPATH' not in os.environ\n"
                        "assert os.environ['AETHRON_REPRODUCTION_TEST'] == 'preserved'\n"
                        "out = Path('build/probes')\n"
                        "out.mkdir(parents=True, exist_ok=True)\n"
                        "(out / Path(__file__).name).write_text('passed', encoding='utf-8')\n"
                    )
                    for name in ("verify.py", "check_ecosystem_plan.py", "edge_package_check.py"):
                        (scripts / name).write_text(probe, encoding="utf-8")
                    # The last real child exports proof of all three stages before cleanup.
                    with (scripts / "edge_package_check.py").open("a", encoding="utf-8") as stream:
                        stream.write(
                            "package = Path(sys.argv[sys.argv.index('--out') + 1])\n"
                            "package.mkdir()\n"
                            "(package / 'probes.json').write_text(\n"
                            "    json.dumps(sorted(p.name for p in out.iterdir())),\n"
                            "    encoding='utf-8')\n"
                        )
                    (source / ".gitignore").write_text("build/\n", encoding="utf-8")
                    for args in (
                        ["init", "--quiet"],
                        ["add", "."],
                        [
                            "-c",
                            "user.name=Reproduction Fixture",
                            "-c",
                            "user.email=fixture@example.invalid",
                            "-c",
                            "commit.gpgsign=false",
                            "-c",
                            "core.hooksPath=" + str(root / "no-hooks"),
                            "commit",
                            "--quiet",
                            "-m",
                            "synthetic Python probes",
                        ],
                    ):
                        subprocess.run(
                            ["git", *args], cwd=source, check=True, capture_output=True, timeout=5
                        )
                    inherited = {
                        "PYTHONHOME": str(foreign_home),
                        "PYTHONPATH": str(foreign_path),
                        "AETHRON_REPRODUCTION_TEST": "preserved",
                    }
                    with (
                        patch.object(edge_reproduce, "ROOT", source),
                        patch.dict(os.environ, inherited),
                        contextlib.redirect_stdout(io.StringIO()) as output,
                        contextlib.redirect_stderr(io.StringIO()),
                    ):
                        edge_reproduce.run(root / "wheelhouse")
                        for name, value in inherited.items():
                            self.assertEqual(os.environ[name], value)
                    self.assertIn("PASS:", output.getvalue())
                    area = source / "build/ecosystem-phase1"
                    packages = list(area.glob("*-package"))
                    self.assertEqual(len(packages), 1)
                    self.assertEqual(
                        (packages[0] / "probes.json").read_text(encoding="utf-8"),
                        '["check_ecosystem_plan.py", "edge_package_check.py", "verify.py"]',
                    )
                    self.assertEqual(list(area.iterdir()), packages)

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
    def test_repeated_attempts_preserve_separate_package_evidence(self):
        for legacy_output in (False, True):
            for first_failed in (False, True):
                with self.subTest(legacy=legacy_output, first_failed=first_failed):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        area = root / "build/ecosystem-phase1"
                        legacy = area / "clean-package"
                        if legacy_output:
                            legacy.mkdir(parents=True)
                            (legacy / "result.json").write_bytes(b"prior evidence")
                        packages, clones, messages = [], [], []
                        failure = subprocess.CalledProcessError(7, ["synthetic-package"])

                        def child(
                            args,
                            clones=clones,
                            packages=packages,
                            first_failed=first_failed,
                            failure=failure,
                            **kwargs,
                        ):
                            self.assertTrue(kwargs["check"])
                            if args[0] == "git":
                                clone = Path(args[-1])
                                clone.mkdir()
                                clones.append(clone)
                            elif args[1] == "scripts/edge_package_check.py":
                                package = Path(args[args.index("--out") + 1])
                                # Same exclusive output admission as the package checker.
                                package.mkdir(parents=True, exist_ok=False)
                                packages.append(package)
                                (package / "server.log").write_bytes(
                                    b"first attempt" if len(packages) == 1 else b"second attempt"
                                )
                                if first_failed and len(packages) == 1:
                                    raise failure
                                (package / "result.json").write_bytes(b"synthetic success")
                            return subprocess.CompletedProcess(args, 0)

                        with (
                            patch.object(edge_reproduce, "ROOT", root),
                            patch.object(edge_reproduce.subprocess, "run", side_effect=child),
                            patch.object(
                                edge_reproduce.subprocess, "check_output", return_value="a" * 40
                            ),
                            patch.object(edge_reproduce, "validate_source"),
                        ):
                            for attempt in range(2):
                                output, diagnostics = io.StringIO(), io.StringIO()
                                error = None
                                with (
                                    contextlib.redirect_stdout(output),
                                    contextlib.redirect_stderr(diagnostics),
                                ):
                                    try:
                                        edge_reproduce.run(root / "wheelhouse")
                                    except Exception as caught:
                                        error = caught
                                self.assertIs(
                                    error, failure if first_failed and attempt == 0 else None
                                )
                                messages.append(diagnostics.getvalue())
                                self.assertEqual("PASS:" in output.getvalue(), error is None)
                                self.assertEqual(clones[attempt].exists(), error is not None)

                        self.assertEqual(len(set(packages)), 2)
                        for index, package in enumerate(packages):
                            self.assertIn(str(package), messages[index])
                            self.assertEqual(
                                (package / "server.log").read_bytes(),
                                b"first attempt" if index == 0 else b"second attempt",
                            )
                            self.assertEqual(
                                (package / "result.json").exists(),
                                not (first_failed and index == 0),
                            )
                        if legacy_output:
                            self.assertEqual(
                                (legacy / "result.json").read_bytes(), b"prior evidence"
                            )

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
                        self.assertIn("package evidence directory:", diagnostics.getvalue())
                    else:
                        self.assertEqual(len(calls), failed_stage + 1)
                        self.assertTrue(workspace.is_dir(), "failed run erased its evidence")
                        self.assertEqual(
                            (clones[0] / "partial.bin").read_bytes(), b"partial\x00evidence"
                        )
                        self.assertIn(str(workspace), diagnostics.getvalue())
                        self.assertEqual(output.getvalue(), "")
