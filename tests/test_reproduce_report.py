"""Synthetic process results test reporting only; no build or product is executed."""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import reproduce


class ReproductionReport(unittest.TestCase):
    def test_source_validation_with_real_git_changes(self):
        for mutation in (None, "ignored", "modified", "deleted", "staged", "untracked", "revision"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                clone = Path(directory)

                def git(*args, clone=clone):
                    return subprocess.check_output(
                        [
                            "git",
                            "-c",
                            "user.name=Reproduction Fixture",
                            "-c",
                            "user.email=fixture@example.invalid",
                            "-c",
                            "commit.gpgsign=false",
                            "-c",
                            "core.hooksPath=" + str(clone / "no-hooks"),
                            *args,
                        ],
                        cwd=clone,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                    ).strip()

                git("init", "--quiet")
                source = clone / "source.txt"
                source.write_bytes(b"original source\n")
                (clone / ".gitignore").write_bytes(b"build/\n")
                git("add", "source.txt", ".gitignore")
                git("commit", "--quiet", "-m", "synthetic source")
                revision = git("rev-parse", "HEAD")
                if mutation in ("modified", "staged"):
                    source.write_bytes(b"changed source\n")
                    if mutation == "staged":
                        git("add", "source.txt")
                elif mutation == "deleted":
                    source.unlink()
                elif mutation == "untracked":
                    (clone / "extra.txt").write_bytes(b"extra source\n")
                    # The checker must override a user preference hiding untracked files.
                    git("config", "status.showUntrackedFiles", "no")
                elif mutation == "revision":
                    # Even a clean new commit with identical source cannot relabel evidence.
                    git("commit", "--quiet", "--allow-empty", "-m", "different revision")
                elif mutation == "ignored":
                    (clone / "build").mkdir()
                    (clone / "build" / "output.txt").write_bytes(b"ignored output\n")
                if mutation in (None, "ignored"):
                    reproduce.validate_source(clone, revision)
                else:
                    with self.assertRaisesRegex(ValueError, "^reproduction_source_changed$"):
                        reproduce.validate_source(clone, revision)

    def test_optimized_execution_is_rejected_before_cloning(self):
        for flag in ("-O", "-OO"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(
                    [sys.executable, "-I", flag, str(Path(reproduce.__file__).resolve())],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.strip(), "reproduce_requires_assertions")
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_checked_call_preserves_arguments_and_rejects_failed_child(self):
        # Removing check=True or introducing shell interpretation must fail this test.
        argument = 'space ; $name "quoted" * & |'
        code = "import sys; print(repr(sys.argv[1])); sys.exit(int(sys.argv[2]))"
        with tempfile.TemporaryDirectory(prefix="report-call-") as directory:
            for status in (0, 7):
                with self.subTest(status=status):
                    args = [sys.executable, "-I", "-S", "-c", code, argument, str(status)]
                    if status:
                        with self.assertRaises(subprocess.CalledProcessError) as caught:
                            reproduce.call(args, directory, capture_output=True, timeout=5)
                        result = caught.exception
                    else:
                        result = reproduce.call(args, directory, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, status)
                    self.assertEqual(result.stdout.decode().strip(), repr(argument))
                    self.assertEqual(result.stderr, b"")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def invoke(
        self,
        *,
        evaluation=0,
        mismatch=None,
        refusal=1,
        consumer=0,
        mutation=None,
        mutate_at=1,
        mutate_lane="a",
        real_consumers=False,
        source_mutation=None,
        source_mutate_at="consumer2",
    ):
        output = io.StringIO()
        consumers = []
        payload = b"synthetic archive placeholder, never executed"
        if real_consumers:
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    "__main__.py",
                    "import importlib.util\n"
                    "assert importlib.util.find_spec('zip_shadow') is None\n"
                    "from aethron import evaluate; evaluate(b'{}')\n",
                )
                bundle.writestr(
                    "aethron/__init__.py",
                    "def evaluate(data):\n    return {'recommendation': {'action': 'STOP'}}\n",
                )
            payload = archive.getvalue()
        revision = "a" * 40
        clone_revision = revision
        source_status = b""
        real_process = subprocess.run

        def fake_process(args, **kwargs):
            nonlocal clone_revision, source_status
            stage = None
            if args[1:2] == ["scripts/verify.py"]:
                stage = "verify"
            elif args[1:2] == ["scripts/release.py"] and Path(args[-1]).name == "b":
                stage = "build"
            elif args[1:2] == ["-I"]:
                stage = "consumer" + str(len(consumers) + 1)
            if source_mutation and stage == source_mutate_at:
                if source_mutation == "revision":
                    clone_revision = "b" * 40
                else:
                    source_status = b" M changed-source.py\n"
            if args[:2] == ["git", "clone"]:
                (Path(args[-1]) / "aethron").mkdir(parents=True)
                examples = Path(args[-1]) / "examples"
                examples.mkdir()
                (examples / "person-blackout.json").write_bytes(b"{}")
            elif args[1:2] == ["scripts/temporal_evaluate.py"]:
                return subprocess.CompletedProcess(args, evaluation)
            elif args[1:2] == ["scripts/release.py"]:
                destination = Path(args[-1])
                if destination.name == "refused":
                    return subprocess.CompletedProcess(
                        args, refusal, stderr=b"release requires clean committed source"
                    )
                destination.mkdir()
                changed = destination.name == "b"
                name = "unexpected.pyz" if changed and mismatch == "names" else "aethron.pyz"
                data = b"different bytes" if changed and mismatch == "bytes" else payload
                (destination / name).write_bytes(data)
            elif args[1:2] == ["scripts/verify.py"] or args[1:3] == ["-m", "aethron"]:
                pass
            elif args[1:2] == ["-I"] or args[1].endswith("aethron.pyz"):
                consumers.append(args)
                if mutation is not None and len(consumers) == mutate_at:
                    artifact = Path(kwargs["cwd"]) / mutate_lane / "aethron.pyz"
                    if mutation == "changed":
                        artifact.write_bytes(b"changed after comparison")
                    elif mutation == "removed":
                        artifact.unlink()
                    elif mutation == "extra":
                        artifact.with_name("uncompared.zip").write_bytes(b"extra artifact")
                    elif mutation == "file_link":
                        target = artifact.parent.parent / "external.pyz"
                        artifact.replace(target)
                        artifact.symlink_to(target)
                    elif mutation == "directory_link":
                        directory = artifact.parent
                        target = directory.with_name("external-build")
                        directory.replace(target)
                        directory.symlink_to(target, target_is_directory=True)
                if consumer:
                    if kwargs.get("check"):
                        raise subprocess.CalledProcessError(consumer, args)
                    return subprocess.CompletedProcess(args, consumer)
                if real_consumers:
                    return real_process(args, **kwargs)
            else:
                self.fail(f"Unexpected process request: {args}")
            return subprocess.CompletedProcess(args, 0)

        def git_output(args, **kwargs):
            if args == ["git", "rev-parse", "HEAD"]:
                return clone_revision + "\n"
            if args == ["git", "status", "--porcelain", "--untracked-files=normal"]:
                return source_status
            self.fail(f"Unexpected Git request: {args}")

        error = None
        with (
            patch.object(reproduce.subprocess, "run", side_effect=fake_process),
            patch.object(reproduce.subprocess, "check_output", side_effect=git_output),
            contextlib.redirect_stdout(output),
        ):
            try:
                reproduce.run()
            except (
                SystemExit,
                AssertionError,
                ValueError,
                subprocess.CalledProcessError,
            ) as caught:
                error = caught
        return output.getvalue(), error, consumers, payload, revision

    def test_source_changes_cannot_be_reported_as_clean_or_relabel_revision(self):
        for stage, consumed in (("verify", 0), ("build", 0), ("consumer1", 1), ("consumer2", 2)):
            for mutation in ("dirty", "revision"):
                with self.subTest(stage=stage, mutation=mutation):
                    output, error, consumers, _, _ = self.invoke(
                        source_mutation=mutation, source_mutate_at=stage
                    )
                    self.assertIsInstance(error, ValueError)
                    self.assertEqual(str(error), "reproduction_source_changed")
                    self.assertEqual(output, "")
                    self.assertEqual(len(consumers), consumed)

    def test_success_reports_compared_bytes_and_clone_revision(self):
        output, error, consumers, payload, revision = self.invoke()
        self.assertIsNone(error)
        self.assertEqual(len(consumers), 2)
        report = json.loads(output)
        self.assertEqual(report["source_revision"], revision)
        self.assertEqual(
            report["artifact_sha256"], {"aethron.pyz": hashlib.sha256(payload).hexdigest()}
        )
        for field in (
            "clean_clone",
            "evaluation_gate_passed",
            "quickstart",
            "isolated_zipapp_consumer",
            "byte_identical_builds",
        ):
            self.assertIs(report[field], True)

    def test_failed_or_terminated_evaluation_cannot_report_overall_success(self):
        for returncode in (1, -15):
            with self.subTest(returncode=returncode):
                output, error, consumers, _, _ = self.invoke(evaluation=returncode)
                self.assertIsInstance(error, SystemExit)
                self.assertNotIn(error.code, (None, 0))
                report = json.loads(output)
                self.assertIs(report["evaluation_gate_passed"], False)
                self.assertIs(report["quickstart"], False)
                self.assertIs(report["byte_identical_builds"], True)
                self.assertIs(report["isolated_zipapp_consumer"], True)
                self.assertEqual(len(consumers), 2)

    def test_artifact_mismatch_stops_before_consumers_and_report(self):
        for mismatch in ("names", "bytes"):
            with self.subTest(mismatch=mismatch):
                output, error, consumers, _, _ = self.invoke(mismatch=mismatch)
                self.assertIsInstance(error, AssertionError)
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_accepted_dirty_source_cannot_produce_report(self):
        output, error, consumers, _, _ = self.invoke(refusal=0)
        self.assertIsInstance(error, AssertionError)
        self.assertEqual(output, "")
        self.assertEqual(consumers, [])

    def test_failed_consumer_cannot_produce_report(self):
        output, error, consumers, _, _ = self.invoke(consumer=1)
        self.assertIsInstance(error, subprocess.CalledProcessError)
        self.assertEqual(output, "")
        self.assertEqual(len(consumers), 1)

    def test_changed_artifacts_cannot_be_reported_as_compared(self):
        for lane in ("a", "b"):
            for mutation in ("changed", "extra", "removed"):
                for mutate_at in (1, 2):
                    with self.subTest(lane=lane, mutation=mutation, mutate_at=mutate_at):
                        output, error, consumers, _, _ = self.invoke(
                            mutation=mutation, mutate_at=mutate_at, mutate_lane=lane
                        )
                        self.assertIsInstance(error, ValueError)
                        self.assertEqual(str(error), "release_artifacts_changed")
                        self.assertEqual(output, "")
                        self.assertEqual(len(consumers), mutate_at)

    def test_linked_artifacts_cannot_be_reported_as_compared(self):
        for lane in ("a", "b"):
            for mutation in ("file_link", "directory_link"):
                for mutate_at in (1, 2):
                    with self.subTest(lane=lane, mutation=mutation, mutate_at=mutate_at):
                        output, error, consumers, _, _ = self.invoke(
                            mutation=mutation, mutate_at=mutate_at, mutate_lane=lane
                        )
                        self.assertIsInstance(error, ValueError)
                        self.assertEqual(str(error), "release_artifacts_changed")
                        self.assertEqual(output, "")
                        self.assertEqual(len(consumers), mutate_at)

    def test_zip_consumers_ignore_caller_import_path(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "aethron"
            package.mkdir()
            (package / "__init__.py").write_text(
                "raise RuntimeError('caller package imported')\n", encoding="utf-8"
            )
            # An unrelated caller module must not be visible to the archive.
            (Path(directory) / "zip_shadow.py").write_text(
                "raise RuntimeError('caller import path leaked')\n", encoding="utf-8"
            )
            for variable in ("PYTHONHOME", "PYTHONPATH"):
                with self.subTest(variable=variable), patch.dict(os.environ, {variable: directory}):
                    output, error, consumers, _, _ = self.invoke(real_consumers=True)
                    self.assertIsNone(error)
                    self.assertEqual(len(consumers), 2)
                    self.assertIs(json.loads(output)["isolated_zipapp_consumer"], True)
