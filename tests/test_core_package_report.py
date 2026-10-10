"""Package reports must not infer dependency counts from mocked consumer success."""

import contextlib
import hashlib
import io
import json
import subprocess
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
                    return real_process(args, **kwargs)
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

    def test_child_failure_never_emits_success_report(self):
        # Two builds, environment creation, install, console and two module consumers.
        for fail_at in range(1, 8):
            with self.subTest(fail_at=fail_at), self.fixture(fail_at=fail_at) as fixture:
                output, _, calls = fixture
                with self.assertRaises(subprocess.CalledProcessError) as raised:
                    package_check.run()
                self.assertEqual(raised.exception.returncode, 7)
                self.assertEqual(len(calls), fail_at)
                self.assertEqual(output.getvalue(), "")

    def test_install_and_report_bind_the_compared_snapshot(self):
        read_bytes = Path.read_bytes
        temporary_directory = package_check.tempfile.TemporaryDirectory
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
                        package_check.tempfile,
                        "TemporaryDirectory",
                        side_effect=lambda **kwargs: temporary_directory(prefix="wheel # space "),
                    ),
                ):
                    output, installed, calls = fixture
                    package_check.run()
                    path, compared = observed[0]
                    digest = hashlib.sha256(compared).hexdigest()
                    self.assertEqual(installed, [path.resolve().as_uri() + "#sha256=" + digest])
                    install = next(call for call in calls if call[1:4] == ["-m", "pip", "install"])
                    self.assertIn("--require-hashes", install)
                    self.assertIn("--force-reinstall", install)
                    self.assertEqual(json.loads(output.getvalue())["sha256"], digest)
                    self.assertEqual(len(observed), 1, "report must not reread a mutable artifact")

    def test_installed_console_launcher_is_required(self):
        with patch.dict(
            package_check.os.environ, {"PYTHONPATH": "untrusted", "PYTHONHOME": "untrusted"}
        ):
            with self.fixture() as (output, _, calls):
                package_check.run()
                self.assertEqual(sum(call[1:] == ["--help"] for call in calls), 1)
                self.assertIs(json.loads(output.getvalue())["console_wrapper"], True)

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
