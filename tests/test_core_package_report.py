"""Package reports must not infer dependency counts from mocked consumer success."""

import contextlib
import hashlib
import io
import json
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_check


class CorePackageReport(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, requirements="", fail_at=None, on_call=None):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            wheel.writestr(
                "aethron-0.2.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: aethron\nVersion: 0.2.0\n" + requirements,
            )
        output = io.StringIO()
        installed = []
        calls = []

        def fake_process(args, *, archive=archive, installed=installed, **kwargs):
            if args[1:4] == ["-m", "build", "--no-isolation"]:
                destination = Path(args[args.index("--outdir") + 1])
                destination.mkdir()
                (destination / "aethron-0.2.0-py3-none-any.whl").write_bytes(archive.getvalue())
            elif args[1:3] == ["-m", "venv"]:
                pass
            elif args[1:4] == ["-m", "pip", "install"]:
                self.assertIn("--no-deps", args)
                self.assertIn("--no-index", args)
                installed.append(args[-1])
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
        # Two builds, environment creation, install, and two consumers.
        for fail_at in range(1, 7):
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
