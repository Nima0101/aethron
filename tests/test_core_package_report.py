"""Package reports must not infer dependency counts from mocked consumer success."""

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_check


class CorePackageReport(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(
        self,
        requirements="",
        fail_at=None,
        on_call=None,
        console_error=None,
        real_install=False,
        installed_defect=None,
        console_output="usage: aethron [-h] {demo,replay,evaluate,render} ...\n",
    ):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            wheel.writestr(
                "aethron-0.2.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: aethron\nVersion: 0.2.0\n" + requirements,
            )
            wheel.writestr("aethron/__init__.py", "")
            wheel.writestr(
                "aethron/__main__.py",
                'def main():\n    print("synthetic installed console help")\n',
            )
            wheel.writestr(
                "aethron-0.2.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            wheel.writestr(
                "aethron-0.2.0.dist-info/entry_points.txt",
                "[console_scripts]\naethron = aethron.__main__:main\n",
            )
            wheel.writestr("aethron-0.2.0.dist-info/RECORD", "")
        with zipfile.ZipFile(archive) as wheel:
            source_payload = {
                name: wheel.read(name) for name in wheel.namelist() if name.startswith("aethron/")
            }
        real_process = subprocess.run
        output = io.StringIO()
        installed = []
        calls = []

        def fake_process(args, *, archive=archive, installed=installed, **kwargs):
            if args[1:4] == ["-m", "build", "--no-isolation"]:
                destination = Path(args[args.index("--outdir") + 1])
                destination.mkdir()
                (destination / "aethron-0.2.0-py3-none-any.whl").write_bytes(archive.getvalue())
            elif args[1:3] == ["-m", "venv"]:
                if real_install:
                    return real_process(args, **kwargs)
            elif args[1:4] == ["-m", "pip", "install"]:
                self.assertIn("--no-deps", args)
                self.assertIn("--no-index", args)
                installed.append(args[-1])
                if real_install:
                    result = real_process(args, stderr=subprocess.PIPE, text=True, **kwargs)
                    if installed_defect is not None:
                        python = args[0]
                        location = real_process(
                            [
                                python,
                                "-I",
                                "-c",
                                "import importlib.metadata; "
                                "print(importlib.metadata.distribution('aethron').locate_file('aethron'))",
                            ],
                            check=True,
                            capture_output=True,
                            text=True,
                        )
                        package = Path(location.stdout.strip())
                        if installed_defect == "changed":
                            (package / "__init__.py").write_bytes(b"# changed after installation\n")
                        elif installed_defect == "missing":
                            (package / "__init__.py").unlink()
                        elif installed_defect == "extra":
                            (package / "unexpected.py").write_bytes(b"# untracked source\n")
                    return result
            elif args[1] == "-I" and args[-1] == "--installed-payload":
                if real_install:
                    return real_process(args, **kwargs)
                with zipfile.ZipFile(io.BytesIO(archive.getvalue())) as wheel:
                    manifest = {
                        name: hashlib.sha256(wheel.read(name)).hexdigest()
                        for name in ("aethron/__init__.py", "aethron/__main__.py")
                    }
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(manifest))
            elif args[1:] == ["--help"]:
                if console_error is not None:
                    raise console_error
                launcher = Path(args[0])
                self.assertEqual(
                    launcher.parent.name, "Scripts" if package_check.os.name == "nt" else "bin"
                )
                self.assertEqual(
                    launcher.name, "aethron.exe" if package_check.os.name == "nt" else "aethron"
                )
                self.assertEqual(launcher.parent.parent.name, "consumer")
                self.assertEqual(Path(kwargs["cwd"]), launcher.parent.parent.parent)
                self.assertNotIn("PYTHONPATH", kwargs["env"])
                self.assertNotIn("PYTHONHOME", kwargs["env"])
                self.assertEqual(kwargs["env"]["PYTHONNOUSERSITE"], "1")
                self.assertTrue(kwargs["check"])
                self.assertEqual(kwargs["timeout"], 30)
                if real_install:
                    result = real_process(args, **kwargs)
                    self.assertEqual(result.stdout.strip(), "synthetic installed console help")
                    return result
                return subprocess.CompletedProcess(args, 0, stdout=console_output)
            elif args[1:5] == ["-I", "-m", "aethron", "demo"]:
                row = {
                    "scenario": "person-zero-visible-thermal",
                    "result": {
                        "recommendation": {"action": "STOP"},
                        "claims": [{"capability": "human_presence", "sources": ["thermal_person"]}],
                    },
                }
                return subprocess.CompletedProcess(
                    args, 0, stdout="\n".join([json.dumps(row)] * 22)
                )
            elif args[1:5] == ["-I", "-m", "aethron", "replay"]:
                row = {"tracks": [{"id": "synthetic", "sources": ["depth", "lwir", "radar"]}]}
                return subprocess.CompletedProcess(
                    args, 0, stdout="\n".join([json.dumps(row)] * 24)
                )
            else:
                self.fail(f"unexpected subprocess request: {args}")
            return subprocess.CompletedProcess(args, 0)

        def process(args, **kwargs):
            calls.append(args)
            if on_call is not None:
                on_call(args)
            result = fake_process(args, **kwargs)
            if len(calls) == fail_at:
                if kwargs.get("check", False):
                    raise subprocess.CalledProcessError(7, args)
                result.returncode = 7
            return result

        with (
            tempfile.TemporaryDirectory() as sandbox,
            patch.object(tempfile, "tempdir", sandbox),
            patch.object(package_check, "snapshot_source_payload", return_value=source_payload),
            patch.object(package_check.subprocess, "run", side_effect=process),
            contextlib.redirect_stdout(output),
        ):
            yield output, installed, calls

    def test_uninspected_metadata_cannot_establish_zero_dependencies(self):
        for requirements in ("", "Requires-Dist: example-dependency>=1\n"):
            with self.subTest(requirements=requirements), self.fixture(requirements) as fixture:
                output, installed, _ = fixture
                package_check.run()
                self.assertEqual(len(installed), 1)
                report = json.loads(output.getvalue())
                self.assertNotIn("runtime_dependencies", report)
                self.assertIs(report["dependency_installation"], False)
                self.assertEqual(report["source_payload_files"], 2)
                self.assertIs(report["installed_source_payload"], True)

    def test_child_failure_never_emits_success_report(self):
        # Two builds, environment, install, payload probe, console and two consumers.
        for fail_at in range(1, 9):
            with self.subTest(fail_at=fail_at), self.fixture(fail_at=fail_at) as fixture:
                output, _, calls = fixture
                with self.assertRaises(subprocess.CalledProcessError) as raised:
                    package_check.run()
                self.assertEqual(raised.exception.returncode, 7)
                self.assertEqual(len(calls), fail_at)
                self.assertEqual(output.getvalue(), "")

    def test_stalled_children_are_bounded_and_retain_failure_evidence(self):
        # Each stage must supply a finite timeout before starting its child.
        for fail_at in range(1, 9):
            with self.subTest(fail_at=fail_at), self.fixture() as fixture:
                output, _, calls = fixture
                process = package_check.subprocess.run.side_effect
                failure = subprocess.TimeoutExpired(
                    ["stalled-package-child"], 1, output=b"partial output", stderr=b"diagnostic"
                )

                def stall(
                    args,
                    *,
                    calls=calls,
                    fail_at=fail_at,
                    failure=failure,
                    process=process,
                    **kwargs,
                ):
                    if len(calls) + 1 == fail_at:
                        timeout = kwargs.get("timeout")
                        self.assertIsInstance(timeout, (int, float))
                        self.assertGreater(timeout, 0)
                        self.assertLessEqual(timeout, 180)
                        calls.append(args)
                        raise failure
                    return process(args, **kwargs)

                diagnostics = io.StringIO()
                with (
                    patch.object(package_check.subprocess, "run", side_effect=stall),
                    contextlib.redirect_stderr(diagnostics),
                    self.assertRaises(subprocess.TimeoutExpired) as raised,
                ):
                    package_check.run()
                workspace = Path(calls[0][-1]).parent
                self.assertIs(raised.exception, failure)
                self.assertEqual(raised.exception.output, b"partial output")
                self.assertEqual(raised.exception.stderr, b"diagnostic")
                self.assertEqual(len(calls), fail_at, "no retry or later consumer after timeout")
                self.assertEqual(output.getvalue(), "")
                self.assertTrue(workspace.is_dir(), "timeout evidence was deleted")
                self.assertIn(str(workspace), diagnostics.getvalue())

    def test_failed_children_retain_package_evidence(self):
        for fail_at in range(1, 9):
            with self.subTest(fail_at=fail_at), self.fixture(fail_at=fail_at) as fixture:
                output, _, calls = fixture
                diagnostics = io.StringIO()
                with contextlib.redirect_stderr(diagnostics):
                    with self.assertRaises(subprocess.CalledProcessError) as raised:
                        package_check.run()
                workspace = Path(calls[0][-1]).parent
                self.assertEqual(raised.exception.returncode, 7)
                self.assertEqual(len(calls), fail_at)
                self.assertEqual(output.getvalue(), "")
                self.assertTrue(workspace.is_dir(), "failed package evidence was deleted")
                self.assertIn(str(workspace), diagnostics.getvalue())
                wheels = list((workspace / "a").glob("*.whl"))
                self.assertEqual(len(wheels), 1)
                with zipfile.ZipFile(wheels[0]) as wheel:
                    self.assertIn("aethron/__init__.py", wheel.namelist())

    def test_interrupted_package_run_retains_original_failure_and_evidence(self):
        for failure in (SystemExit(9), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):

                def interrupt(args, failure=failure):
                    if args[1:3] == ["-m", "venv"]:
                        raise failure

                with self.fixture(on_call=interrupt) as (output, _, calls):
                    diagnostics = io.StringIO()
                    with contextlib.redirect_stderr(diagnostics):
                        with self.assertRaises(type(failure)) as raised:
                            package_check.run()
                    workspace = Path(calls[0][-1]).parent
                    self.assertIs(raised.exception, failure)
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(len(calls), 3)
                    self.assertTrue(workspace.is_dir(), "interrupted evidence was deleted")
                    self.assertIn(str(workspace), diagnostics.getvalue())
                    self.assertEqual(len(list(workspace.glob("*/*.whl"))), 2)

    def test_successful_package_run_cleans_workspace(self):
        with self.fixture() as (output, _, calls):
            package_check.run()
            self.assertFalse(Path(calls[0][-1]).parent.exists())
            self.assertIs(json.loads(output.getvalue())["isolated_install"], True)

    def test_install_and_report_bind_the_compared_snapshot(self):
        read_bytes = Path.read_bytes
        workspace = package_check.reproduction_workspace
        for mutation in ("after_read", "before_install", "after_install"):
            with self.subTest(mutation=mutation):
                observed = []

                def read_snapshot(path, observed=observed, mutation=mutation):
                    data = read_bytes(path)
                    if path.parent.name == "a" and path.suffix == ".whl":
                        observed.append((path, data))
                        if mutation == "after_read":
                            path.write_bytes(b"replaced after comparison read")
                    return data

                def mutate(args, observed=observed, mutation=mutation):
                    trigger = (mutation == "before_install" and args[1:3] == ["-m", "venv"]) or (
                        mutation == "after_install"
                        and args[1:5] == ["-I", "-m", "aethron", "replay"]
                    )
                    if trigger:
                        observed[0][0].write_bytes(b"replaced at consumer boundary")

                with (
                    self.fixture(on_call=mutate) as fixture,
                    patch.object(Path, "read_bytes", read_snapshot),
                    patch.object(
                        package_check,
                        "reproduction_workspace",
                        side_effect=lambda **kwargs: workspace(prefix="wheel # space "),
                    ),
                ):
                    output, installed, calls = fixture
                    with self.assertRaisesRegex(ValueError, "wheel_artifacts_changed"):
                        package_check.run()
                    path, compared = observed[0]
                    digest = hashlib.sha256(compared).hexdigest()
                    self.assertEqual(installed, [path.resolve().as_uri() + "#sha256=" + digest])
                    install = next(call for call in calls if call[1:4] == ["-m", "pip", "install"])
                    self.assertIn("--require-hashes", install)
                    self.assertIn("--force-reinstall", install)
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(
                        len(observed), 2, "final integrity must recheck compared bytes"
                    )

    def test_installed_console_launcher_is_required(self):
        with patch.dict(
            package_check.os.environ, {"PYTHONPATH": "untrusted", "PYTHONHOME": "untrusted"}
        ):
            with self.fixture() as (output, _, calls):
                package_check.run()
                self.assertEqual(sum(call[1:] == ["--help"] for call in calls), 1)
                self.assertIs(json.loads(output.getvalue())["console_wrapper"], True)

    def test_parent_python_settings_do_not_redirect_environment_or_install(self):
        with tempfile.TemporaryDirectory() as directory:
            shadow = Path(directory)
            (shadow / "venv.py").write_text(
                'raise RuntimeError("inherited path redirected venv")\n', encoding="utf-8"
            )
            (shadow / "pip.py").write_text(
                'raise RuntimeError("inherited path redirected pip")\n', encoding="utf-8"
            )
            for variable, value in (
                ("PYTHONHOME", str(shadow / "missing-python-home")),
                ("PYTHONPATH", str(shadow)),
            ):
                with (
                    self.subTest(variable=variable),
                    patch.dict(package_check.os.environ, {variable: value}),
                    self.fixture(real_install=True) as (output, installed, calls),
                ):
                    package_check.run()
                    self.assertEqual(package_check.os.environ[variable], value)
                    self.assertEqual(len(installed), 1)
                    self.assertEqual(len(calls), 8)
                    self.assertIs(json.loads(output.getvalue())["isolated_install"], True)

    def test_real_pip_rejects_changed_wheel_before_consumers(self):
        wheels = []

        def replace_before_install(args):
            if args[1:4] == ["-m", "build", "--no-isolation"]:
                wheels.append(Path(args[args.index("--outdir") + 1]))
            elif args[1:4] == ["-m", "pip", "install"]:
                next(wheels[0].glob("*.whl")).write_bytes(b"replaced after comparison")

        with self.fixture(real_install=True, on_call=replace_before_install) as fixture:
            output, _, calls = fixture
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                package_check.run()
            self.assertIn("DO NOT MATCH THE HASHES", raised.exception.stderr)
            self.assertEqual(calls[-1][1:4], ["-m", "pip", "install"])
            self.assertEqual(output.getvalue(), "")

    def test_optimized_execution_cannot_emit_success(self):
        result = subprocess.run(
            [sys.executable, "-I", "-O", str(Path(package_check.__file__).resolve())],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("package_check_requires_assertions", result.stderr)

    def test_launcher_failure_prevents_success_report(self):
        for error in (
            FileNotFoundError("launcher missing"),
            subprocess.CalledProcessError(2, ["launcher"]),
            subprocess.TimeoutExpired(["launcher"], 30),
        ):
            with (
                self.subTest(error=type(error).__name__),
                self.fixture(console_error=error) as (output, _, _),
            ):
                with self.assertRaises(type(error)):
                    package_check.run()
                self.assertEqual(output.getvalue(), "")

    def test_empty_launcher_help_cannot_pass(self):
        with self.fixture(console_output="  \n") as (output, _, _):
            with self.assertRaisesRegex(AssertionError, "console help is empty"):
                package_check.run()
            self.assertEqual(output.getvalue(), "")

    def test_real_synthetic_console_and_missing_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            shadow = Path(directory) / "aethron"
            shadow.mkdir()
            (shadow / "__init__.py").write_text('raise RuntimeError("imported shadow package")\n')
            for missing in (False, True):

                def remove_launcher(args, missing=missing):
                    if missing and args[1:] == ["--help"]:
                        Path(args[0]).unlink()

                with (
                    self.subTest(missing=missing),
                    patch.dict(package_check.os.environ, {"PYTHONPATH": directory}),
                ):
                    with self.fixture(real_install=True, on_call=remove_launcher) as (output, _, _):
                        if missing:
                            with self.assertRaises(FileNotFoundError):
                                package_check.run()
                            self.assertEqual(output.getvalue(), "")
                        else:
                            package_check.run()
                            self.assertIs(json.loads(output.getvalue())["console_wrapper"], True)

    def test_changed_installed_payload_cannot_emit_success(self):
        for defect in ("changed", "missing", "extra"):
            with (
                self.subTest(defect=defect),
                self.fixture(real_install=True, installed_defect=defect) as (output, _, calls),
            ):
                with self.assertRaisesRegex(ValueError, "installed_source_payload_mismatch"):
                    package_check.run()
                self.assertEqual(calls[-1][-1], "--installed-payload")
                self.assertFalse(any(call[1:] == ["--help"] for call in calls))
                self.assertEqual(output.getvalue(), "")

    def test_report_manifest_binds_prebuild_source_snapshot(self):
        with self.fixture() as (output, _, calls):
            manifest = {
                name: hashlib.sha256(data).hexdigest()
                for name, data in package_check.snapshot_source_payload(package_check.ROOT).items()
            }
            package_check.run()
            expected = hashlib.sha256(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            self.assertEqual(json.loads(output.getvalue())["source_payload_sha256"], expected)
            probe = next(call for call in calls if call[-1] == "--installed-payload")
            self.assertEqual(probe[1], "-I")
            self.assertEqual(Path(probe[2]), Path(package_check.__file__).resolve())
