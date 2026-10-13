"""Exercise report publication using synthetic files and mocked package processes."""

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import edge_package_check as checker


@unittest.skipUnless(importlib.util.find_spec("packaging.utils"), "wheel build dependency")
class PackageInputEvidence(unittest.TestCase):
    def probe(
        self,
        vision=False,
        change=None,
        delete=False,
        vision_suite=None,
        reject=False,
        wheel_defect=None,
        installed_defect=None,
        package="aethron_edge",
        mutate_source=False,
        artifact_change=None,
        console_error=None,
        console_output="usage: aethron-edge\n",
    ):
        execute = subprocess.run
        spawn = subprocess.Popen
        names = [
            "scripts/edge_package_check.py",
            "scripts/package_check.py",
            "pyproject.toml",
            "integrations/edge/pyproject.toml",
            "integrations/edge/requirements-server.lock",
        ]
        if vision:
            names.append("integrations/edge/requirements-vision.lock")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            expected = {}
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
                expected[name] = hashlib.sha256(name.encode()).hexdigest()
            payloads = {
                "aethron": {"aethron/__init__.py": b"# core source\n"},
                "aethron_edge": {"aethron_edge/__init__.py": b"# edge source\n"},
            }
            for package_name, payload in payloads.items():
                project = root if package_name == "aethron" else root / "integrations/edge"
                for name, data in payload.items():
                    path = project / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            status_reads = 0
            executed_suites = []
            original_read = Path.read_text

            def copy_fixture(origin, destination):
                name = Path(origin).name
                if name.endswith(".py"):
                    source = ""
                    if name == "test_sensor_packets.py":
                        source = (
                            "import unittest\nclass Case(unittest.TestCase):\n"
                            " def test_one(self): pass\n"
                        )
                    elif name == "test_rectification.py":
                        source = vision_suite
                    Path(destination).write_text(source)

            def read_text(path, *args, **kwargs):
                nonlocal status_reads
                if path.name == "status.json":
                    status_reads += 1
                    return json.dumps({"processed": status_reads})
                return original_read(path, *args, **kwargs)

            consumers = []

            def run(args, **kwargs):
                if args[1:] == ["--help"]:
                    self.assertEqual(Path(args[0]).stem, "aethron-edge")
                    self.assertNotIn("PYTHONPATH", kwargs["env"])
                    self.assertNotIn("PYTHONHOME", kwargs["env"])
                    self.assertEqual(kwargs["env"]["PYTHONNOUSERSITE"], "1")
                    self.assertEqual(kwargs["timeout"], 30)
                    if console_error is not None:
                        raise console_error
                    return subprocess.CompletedProcess(args, 0, stdout=console_output)
                if args[-1] in ("--installed-payload", "--installed-edge-payload"):
                    selected = "aethron" if args[-1] == "--installed-payload" else "aethron_edge"
                    manifest = {
                        name: hashlib.sha256(data).hexdigest()
                        for name, data in payloads[selected].items()
                    }
                    if selected == package:
                        if installed_defect == "changed":
                            manifest[next(iter(manifest))] = "0" * 64
                        elif installed_defect == "missing":
                            manifest.clear()
                        elif installed_defect == "extra":
                            manifest[selected + "/retired.py"] = "0" * 64
                    self.assertEqual(args[1], "-I")
                    return subprocess.CompletedProcess(args, 0, stdout=json.dumps(manifest))
                if "-c" in args:
                    consumers.append(args[-1])
                if vision_suite is not None and "-c" in args:
                    executed_suites.append(args[-1])
                    with patch.object(checker.subprocess, "Popen", spawn):
                        return execute(
                            [sys.executable, *args[1:]],
                            **dict(kwargs, capture_output=True, text=True, timeout=10),
                        )
                if "build" in args:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir(exist_ok=True)
                    for selected, version in (("aethron", "0.2.0"), ("aethron_edge", "0.1.0")):
                        records = list(payloads[selected].items())
                        if selected == package:
                            if wheel_defect == "changed":
                                records[0] = (records[0][0], b"# stale source\n")
                            elif wheel_defect == "missing":
                                records.clear()
                            elif wheel_defect == "extra":
                                records.append((selected + "/retired.py", b"# stale extra\n"))
                            elif wheel_defect == "duplicate":
                                records.append(records[0])
                        wheel = destination / (selected + "-" + version + "-py3-none-any.whl")
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            with zipfile.ZipFile(wheel, "w") as archive:
                                for name, data in records:
                                    # Mock builds must differ only by the requested defect.
                                    member = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                                    archive.writestr(member, data)
                    if mutate_source:
                        (root / "integrations/edge/aethron_edge/__init__.py").write_bytes(
                            b"changed"
                        )
                if any(str(arg).endswith("observe.py") for arg in args) and change:
                    target = root / change
                    if delete:
                        target.unlink()
                    else:
                        target.write_bytes(b"changed after build")
                if any(str(arg).endswith("observe.py") for arg in args) and artifact_change:
                    lane, change_kind = artifact_change
                    target = output / lane / "aethron_edge-0.1.0-py3-none-any.whl"
                    if change_kind == "changed":
                        target.write_bytes(b"changed after consumer")
                    elif change_kind == "missing":
                        target.unlink()
                    else:
                        (output / lane / "unexpected.whl").write_bytes(b"extra")
                return subprocess.CompletedProcess(
                    args, 0, stdout='{"current_state": "UNKNOWN"}\n' * 3
                )

            with ExitStack() as stack:
                stack.enter_context(patch.object(checker, "ROOT", root))
                stack.enter_context(patch.object(checker.subprocess, "run", side_effect=run))
                stack.enter_context(patch.object(checker.subprocess, "Popen"))
                stack.enter_context(
                    patch.object(
                        checker.shutil,
                        "copyfile",
                        side_effect=copy_fixture if vision_suite is not None else None,
                    )
                )
                stack.enter_context(patch.object(checker.time, "sleep"))
                socket = stack.enter_context(patch.object(checker.socket, "socket"))
                socket.return_value.__enter__.return_value.getsockname.return_value = (
                    "127.0.0.1",
                    12345,
                )
                response = stack.enter_context(patch.object(checker.urllib.request, "urlopen"))
                response.return_value.__enter__.return_value.status = 200
                stack.enter_context(patch.object(Path, "read_text", read_text))
                printed = stack.enter_context(redirect_stdout(io.StringIO()))
                if console_error is not None or not console_output.strip():
                    expected_error = (
                        type(console_error) if console_error is not None else ValueError
                    )
                    with self.assertRaises(expected_error):
                        checker.run(root / "wheelhouse", output, vision)
                    self.assertFalse((output / "result.json").exists())
                    self.assertEqual(printed.getvalue(), "")
                    self.assertEqual(consumers, [])
                    return
                if wheel_defect or installed_defect:
                    reason = (
                        "wheel_source_payload_mismatch"
                        if wheel_defect
                        else "installed_source_payload_mismatch"
                    )
                    with self.assertRaisesRegex(ValueError, reason):
                        checker.run(root / "wheelhouse", output, vision)
                    self.assertFalse((output / "result.json").exists())
                    self.assertEqual(printed.getvalue(), "")
                    self.assertEqual(consumers, [], "reject before consumer execution")
                    return
                if reject:
                    with self.assertRaises(subprocess.CalledProcessError):
                        checker.run(root / "wheelhouse", output, vision)
                    self.assertEqual(executed_suites, ["test_sensor*.py", "test*rectification.py"])
                    self.assertFalse((output / "result.json").exists())
                    self.assertEqual(printed.getvalue(), "")
                    return
                if change or artifact_change:
                    reason = "package_input_changed" if change else "package_artifact_changed"
                    with self.assertRaisesRegex(ValueError, reason):
                        checker.run(root / "wheelhouse", output, vision)
                    self.assertFalse((output / "result.json").exists())
                    self.assertEqual(printed.getvalue(), "")
                    return
                checker.run(root / "wheelhouse", output, vision)
                record = json.loads((output / "result.json").read_text())
                self.assertEqual(record.get("observed_input_sha256"), expected)
                self.assertIs(record.get("source_tree_bound"), False)
                self.assertIs(record["installed_source_payload"], True)
                self.assertIs(record["console_wrapper"], True)
                self.assertEqual(record["source_payload_files"], {"aethron": 1, "aethron-edge": 1})
                for selected, payload in payloads.items():
                    manifest = {
                        name: hashlib.sha256(data).hexdigest() for name, data in payload.items()
                    }
                    digest = hashlib.sha256(
                        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    self.assertEqual(
                        record["source_payload_sha256"][selected.replace("_", "-")], digest
                    )
                self.assertEqual(json.loads(printed.getvalue()), record)
                if vision_suite is not None:
                    self.assertEqual(executed_suites, ["test_sensor*.py", "test*rectification.py"])
                    self.assertIs(record["installed_rectification"], True)

    def test_report_identifies_checker_and_manifests(self):
        self.probe()

    def test_vision_report_also_identifies_vision_lock(self):
        self.probe(vision=True)

    def test_fixture_build_clock_cannot_mask_source_validation(self):
        for package in ("aethron", "aethron_edge"):
            for defect in (None, "changed", "missing", "extra", "duplicate"):
                with self.subTest(package=package, defect=defect):
                    # Cross ZIP's two-second timestamp boundary without sleeping.
                    times = [(2026, 1, 1, 0, 0, second) for second in range(0, 60, 2)]
                    with patch.object(zipfile.time, "localtime", side_effect=times):
                        self.probe(wheel_defect=defect, package=package)

    def test_changed_checker_or_manifest_prevents_success_report(self):
        for name in (
            "scripts/edge_package_check.py",
            "scripts/package_check.py",
            "pyproject.toml",
            "integrations/edge/pyproject.toml",
            "integrations/edge/requirements-server.lock",
            "integrations/edge/requirements-vision.lock",
        ):
            with self.subTest(name=name):
                self.probe(vision=True, change=name)

    def test_removed_manifest_prevents_success_report(self):
        self.probe(change="integrations/edge/requirements-server.lock", delete=True)

    def test_optional_suite_incomplete_or_failed_results_prevent_report(self):
        for method in (
            " @unittest.skip('synthetic')\n def test_one(self): pass\n",
            " @unittest.expectedFailure\n def test_one(self): self.fail('synthetic')\n",
            " @unittest.expectedFailure\n def test_one(self): pass\n",
            " def test_one(self): self.fail('synthetic')\n",
        ):
            with self.subTest(method=method):
                self.probe(
                    vision=True,
                    vision_suite="import unittest\nclass Case(unittest.TestCase):\n" + method,
                    reject=True,
                )

    def test_optional_passing_suite_allows_report(self):
        self.probe(
            vision=True,
            vision_suite="import unittest\nclass Case(unittest.TestCase):\n def test_one(self): pass\n",
        )

    def test_stale_missing_extra_or_duplicate_wheel_source_rejects_report(self):
        for package in ("aethron", "aethron_edge"):
            for defect in ("changed", "missing", "extra", "duplicate"):
                with self.subTest(package=package, defect=defect):
                    self.probe(wheel_defect=defect, package=package)

    def test_installed_source_mismatch_rejects_before_consumers(self):
        for package in ("aethron", "aethron_edge"):
            for defect in ("changed", "missing", "extra"):
                with self.subTest(package=package, defect=defect):
                    self.probe(installed_defect=defect, package=package)

    def test_source_binding_uses_prebuild_snapshot(self):
        self.probe(mutate_source=True)

    def test_artifact_changes_after_consumers_prevent_success_report(self):
        for lane in ("a", "b"):
            for change in ("changed", "missing", "extra"):
                with self.subTest(lane=lane, change=change):
                    self.probe(artifact_change=(lane, change))

    def test_console_failure_prevents_consumer_and_report(self):
        for error in (
            FileNotFoundError("synthetic missing launcher"),
            subprocess.CalledProcessError(2, ["synthetic launcher"]),
            subprocess.TimeoutExpired(["synthetic launcher"], 30),
        ):
            with self.subTest(error=type(error).__name__):
                self.probe(console_error=error)
        self.probe(console_output=" \n")
