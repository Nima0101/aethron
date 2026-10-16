"""Exercise report publication with synthetic packages and optional real venv creation."""

import csv
import hashlib
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
import zipfile
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, call, patch

from wheel_fixtures import record_row

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
        on_run=None,
        on_process=None,
        on_exit=None,
        real_venv=False,
        real_install=False,
        server=None,
        health_errors=None,
        health_clock=None,
        status_counts=None,
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
                if name.endswith("pyproject.toml"):
                    version = "0.1.0" if name.startswith("integrations/") else "0.2.0"
                    # Both inert packages run in the core verifier's Python matrix.
                    # This fixture does not import or qualify the real edge runtime.
                    path.write_text(
                        f'[project]\nversion = "{version}"\nrequires-python = ">=3.9"\n'
                        'license = "GPL-3.0-only"\n'
                    )
                expected[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            if real_install:
                probe = root / "scripts/package_check.py"
                probe.write_bytes(Path(checker.package_check.__file__).read_bytes())
                expected["scripts/package_check.py"] = hashlib.sha256(
                    probe.read_bytes()
                ).hexdigest()
            payloads = {
                "aethron": {"aethron/__init__.py": b"# core source\n"},
                "aethron_edge": {"aethron_edge/__init__.py": b"# edge source\n"},
            }
            if real_install:
                for name, payload in payloads.items():
                    payload[name + "/module.py"] = b"# installed source\n"
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
                    return json.dumps(
                        {
                            "processed": status_reads
                            if status_counts is None
                            else next(status_counts)
                        }
                    )
                return original_read(path, *args, **kwargs)

            consumers = []

            def run(args, **kwargs):
                if on_process is not None:
                    on_process(args, kwargs)
                if on_run is not None:
                    on_run(args)
                if (real_venv or real_install) and args[1:3] == ["-m", "venv"]:
                    # Run the actual child so inherited interpreter settings matter.
                    with patch.object(checker.subprocess, "Popen", spawn):
                        try:
                            result = execute(
                                args, **dict(kwargs, capture_output=True, text=True, timeout=30)
                            )
                        except subprocess.CalledProcessError as exc:
                            self.fail(exc.stderr)
                    self.assertTrue((Path(args[-1]) / "pyvenv.cfg").is_file())
                    return result
                if real_install and (
                    "--no-deps" in args
                    or args[-1] in ("--installed-payload", "--installed-edge-payload")
                ):
                    with patch.object(checker.subprocess, "Popen", spawn):
                        return execute(args, **kwargs)
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
                            elif wheel_defect == "nul-name":
                                records.append((selected + "/notes.txt@ignored", b"resource\n"))
                            elif wheel_defect == "script-destination":
                                records.append(
                                    (
                                        selected + "-" + version + ".data/scripts/fixture-tool",
                                        b"# inert\n",
                                    )
                                )
                            elif wheel_defect == "entry-points":
                                records.append(
                                    (
                                        selected + "-" + version + ".dist-info/entry_points.txt",
                                        b"[console_scripts]\nfixture-tool = fixture:main\n",
                                    )
                                )
                        wheel = destination / (selected + "-" + version + "-py3-none-any.whl")
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            with zipfile.ZipFile(wheel, "w") as archive:
                                info = selected + "-" + version + ".dist-info/"
                                records.extend(
                                    (
                                        (
                                            info + "METADATA",
                                            (
                                                f"Metadata-Version: 2.1\nName: {selected.replace('_', '-')}\nVersion: {version}\n"
                                                "Requires-Python: >=3.9\n"
                                                "License-Expression: GPL-3.0-only\n"
                                            ).encode(),
                                        ),
                                        (
                                            info + "WHEEL",
                                            b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                                        ),
                                    )
                                )
                                record = io.StringIO(newline="")
                                csv.writer(record).writerows(
                                    record_row(name, data) for name, data in records
                                )
                                csv.writer(record).writerow((info + "RECORD", "", ""))
                                records.append((info + "RECORD", record.getvalue().encode()))
                                for name, data in records:
                                    # Mock builds must differ only by the requested defect.
                                    member = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                                    archive.writestr(member, data)
                        if selected == package and wheel_defect == "nul-name":
                            wheel.write_bytes(
                                wheel.read_bytes().replace(
                                    b"notes.txt@ignored", b"notes.txt\x00ignored"
                                )
                            )
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
                    elif change_kind == "symlink":
                        relocated = root / "relocated-wheel"
                        target.rename(relocated)
                        target.symlink_to(relocated)
                    elif change_kind == "linked_directory":
                        relocated = root / "relocated-build"
                        (output / lane).rename(relocated)
                        (output / lane).symlink_to(relocated, target_is_directory=True)
                    else:
                        (output / lane / "unexpected.whl").write_bytes(b"extra")
                return subprocess.CompletedProcess(
                    args, 0, stdout='{"current_state": "UNKNOWN"}\n' * 3
                )

            with ExitStack() as stack:
                stack.enter_context(patch.object(checker, "ROOT", root))
                stack.enter_context(patch.object(checker.subprocess, "run", side_effect=run))
                process = stack.enter_context(patch.object(checker.subprocess, "Popen"))
                if server is not None:
                    process.return_value = server
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
                if health_errors is not None:
                    response.side_effect = health_errors
                if health_clock is not None:
                    stack.enter_context(
                        patch.object(checker.time, "monotonic", side_effect=health_clock)
                    )
                stack.enter_context(patch.object(Path, "read_text", read_text))
                printed = stack.enter_context(redirect_stdout(io.StringIO()))
                if on_exit is not None:
                    stack.callback(on_exit, output, printed)
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
                self.assertEqual(
                    record["source_payload_files"],
                    {name.replace("_", "-"): len(payload) for name, payload in payloads.items()},
                )
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

    def test_synthetic_wheels_admit_core_python_matrix(self):
        execute, spawn = subprocess.run, subprocess.Popen
        checked = []

        def on_process(args, kwargs):
            if "--no-deps" not in args:
                return
            for version in ("3.9", "3.13"):
                with self.subTest(version=version):
                    with patch.object(checker.subprocess, "Popen", spawn):
                        result = execute(
                            [
                                sys.executable,
                                *args[1:],
                                "--dry-run",
                                "--ignore-installed",
                                "--python-version",
                                version,
                            ],
                            **dict(
                                kwargs,
                                check=False,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                            ),
                        )
                    checked.append(version)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        self.probe(on_process=on_process)
        self.assertEqual(checked, ["3.9", "3.13"])

    def test_installed_payloads_checked_after_all_consumers(self):
        for vision in (False, True):
            with self.subTest(vision=vision):
                calls = []
                self.probe(vision=vision, on_run=calls.append)
                for flag in ("--installed-payload", "--installed-edge-payload"):
                    probes = [i for i, args in enumerate(calls) if args[-1] == flag]
                    self.assertEqual(len(probes), 2)
                    consumers = [
                        i
                        for i, args in enumerate(calls)
                        if "--help" in args
                        or "-c" in args
                        or any(str(arg).endswith("observe.py") for arg in args)
                    ]
                    self.assertLess(probes[0], min(consumers))
                    self.assertGreater(probes[1], max(consumers))

    def test_final_installed_probe_failure_retains_evidence(self):
        for flag in ("--installed-payload", "--installed-edge-payload"):
            for kind in (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                with self.subTest(flag=flag, kind=kind.__name__):
                    seen = []
                    error = (
                        kind(7, [flag])
                        if kind is subprocess.CalledProcessError
                        else kind([flag], 30)
                    )
                    diagnostics = io.StringIO()

                    def on_process(args, kwargs, flag=flag, seen=seen, error=error):
                        if args[-1] == flag:
                            seen.append(args)
                            self.assertEqual(kwargs["timeout"], 30)
                            self.assertTrue(kwargs["check"])
                            self.assertEqual(args[1], "-I")
                            if len(seen) == 2:
                                raise error

                    def on_exit(output, printed, diagnostics=diagnostics):
                        self.assertFalse((output / "result.json").exists())
                        self.assertEqual(printed.getvalue(), "")
                        self.assertEqual(len(list(output.glob("*/*.whl"))), 4)
                        workspace = next(output.glob("aethron-installed-*"))
                        self.assertIn(str(workspace), diagnostics.getvalue())

                    with redirect_stderr(diagnostics), self.assertRaises(kind) as raised:
                        self.probe(on_process=on_process, on_exit=on_exit)
                    self.assertIs(raised.exception, error)

    def test_real_installed_source_mutations_after_consumers_block_report(self):
        execute, spawn = subprocess.run, subprocess.Popen
        for package in ("aethron", "aethron_edge"):
            for defect in ("changed", "missing", "extra"):
                with self.subTest(package=package, defect=defect):
                    diagnostics = io.StringIO()

                    def on_process(args, kwargs, package=package, defect=defect):
                        # Last optional consumer: use real installed bytes and real
                        # isolated manifest processes; consumer output is synthetic.
                        if args[-1] != "test*rectification.py":
                            return
                        with patch.object(checker.subprocess, "Popen", spawn):
                            execute(
                                [
                                    args[0],
                                    "-I",
                                    "-c",
                                    "import importlib.metadata, pathlib, sys; "
                                    "p = pathlib.Path(importlib.metadata.distribution(sys.argv[1]).locate_file(sys.argv[2])); "
                                    "kind = sys.argv[3]; "
                                    "(p / '__init__.py').write_bytes(b'# changed') if kind == 'changed' else "
                                    "(p / '__init__.py').unlink() if kind == 'missing' else "
                                    "(p / 'extra.py').write_bytes(b'# extra')",
                                    package.replace("_", "-"),
                                    package,
                                    defect,
                                ],
                                check=True,
                                capture_output=True,
                                timeout=30,
                            )

                    def on_exit(output, printed, diagnostics=diagnostics):
                        self.assertFalse((output / "result.json").exists())
                        self.assertEqual(printed.getvalue(), "")
                        self.assertTrue((output / "server.log").is_file())
                        self.assertEqual(len(list(output.glob("*/*.whl"))), 4)
                        workspace = next(output.glob("aethron-installed-*"))
                        self.assertIn(str(workspace), diagnostics.getvalue())

                    with (
                        redirect_stderr(diagnostics),
                        self.assertRaisesRegex(ValueError, "installed_source_payload_mismatch"),
                    ):
                        self.probe(
                            vision=True, real_install=True, on_process=on_process, on_exit=on_exit
                        )

    def test_real_unchanged_installed_sources_qualify(self):
        self.probe(real_install=True)

    def test_dependency_failure_stops_consumers_and_preserves_evidence(self):
        for failing_check in (1, 2):
            for failure_type in (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                with self.subTest(stage=failing_check, failure=failure_type.__name__):
                    calls = []
                    diagnostics = io.StringIO()
                    error = (
                        failure_type(1, ["pip", "check"])
                        if failure_type is subprocess.CalledProcessError
                        else failure_type(["pip", "check"], 30)
                    )

                    def on_process(
                        args, kwargs, calls=calls, failing_check=failing_check, error=error
                    ):
                        calls.append(args)
                        if args[1:] == ["-I", "-m", "pip", "check"]:
                            checks = sum(c[1:] == args[1:] for c in calls)
                            if checks == failing_check:
                                raise error

                    def on_exit(output, printed, diagnostics=diagnostics):
                        self.assertFalse((output / "result.json").exists())
                        self.assertEqual(printed.getvalue(), "")
                        self.assertEqual(len(list(output.glob("*/*.whl"))), 4)
                        workspace = next(output.glob("aethron-installed-*"))
                        self.assertTrue(workspace.is_dir())
                        self.assertIn(str(workspace), diagnostics.getvalue())

                    with redirect_stderr(diagnostics), self.assertRaises(failure_type) as caught:
                        self.probe(vision=True, on_process=on_process, on_exit=on_exit)
                    self.assertIs(caught.exception, error)
                    self.assertEqual(calls[-1][1:], ["-I", "-m", "pip", "check"])
                    suites = [c[-1] for c in calls if "-c" in c]
                    self.assertEqual(suites, [] if failing_check == 1 else ["test_sensor*.py"])

    def test_dependency_compatibility_precedes_each_consumer_stage(self):
        for vision in (False, True):
            with self.subTest(vision=vision):
                calls = []

                def on_process(args, kwargs, calls=calls):
                    calls.append(args)
                    if args[1:] == ["-I", "-m", "pip", "check"]:
                        self.assertTrue(kwargs["check"])
                        self.assertEqual(kwargs["timeout"], 30)
                        self.assertEqual(Path(args[0]).parent.parent.parent, kwargs["cwd"])
                        self.assertNotIn("PYTHONPATH", kwargs["env"])
                        self.assertNotIn("PYTHONHOME", kwargs["env"])

                self.probe(vision=vision, on_process=on_process)
                checks = [i for i, c in enumerate(calls) if c[1:] == ["-I", "-m", "pip", "check"]]
                self.assertEqual(len(checks), 2 if vision else 1)
                payload = next(i for i, c in enumerate(calls) if c[-1] == "--installed-payload")
                self.assertLess(checks[0], payload)
                if vision:
                    install = next(
                        i
                        for i, c in enumerate(calls)
                        if any(str(a).endswith("requirements-vision.lock") for a in c)
                    )
                    suite = next(i for i, c in enumerate(calls) if c[-1] == "test*rectification.py")
                    self.assertLess(install, checks[1])
                    self.assertLess(checks[1], suite)

    def test_invalid_processing_counts_do_not_qualify_viewer_independence(self):
        for counts in (
            [False, True],
            ["10", "2"],
            [-2, -1],
            [1.0, 2.0],
            [[1], [2]],
            [0, True],
            [0, 1.5],
        ):
            with self.subTest(counts=counts):
                self.assert_processing_rejected(counts, "installed_processed_invalid")

    def test_processing_counter_regression_does_not_qualify_recovery(self):
        self.assert_processing_rejected([10, 9, 11], "installed_processed_regressed")

    def assert_processing_rejected(self, counts, reason):
        server = Mock()
        diagnostics = io.StringIO()
        calls = []

        def on_exit(output, printed):
            self.assertFalse((output / "result.json").exists())
            self.assertEqual(printed.getvalue(), "")
            self.assertTrue((output / "server.log").is_file())
            self.assertEqual(len(list(output.glob("*/*.whl"))), 4)
            workspace = next(output.glob("aethron-installed-*"))
            self.assertTrue(workspace.is_dir())
            self.assertIn(str(workspace), diagnostics.getvalue())

        with redirect_stderr(diagnostics), self.assertRaisesRegex(ValueError, "^" + reason + "$"):
            self.probe(
                status_counts=iter(counts),
                server=server,
                vision=True,
                on_run=calls.append,
                on_exit=on_exit,
            )
        self.assertEqual(server.mock_calls, [call.terminate(), call.wait(timeout=10)])
        self.assertFalse(
            any("requirements-vision.lock" in str(arg) for args in calls for arg in args)
        )

    def test_processing_counter_may_stall_then_increase(self):
        self.probe(status_counts=iter([0, 0, 0, 1]))
        self.probe(status_counts=iter([10, 10, 11]))

    def test_server_readiness_expiry_stops_consumers_and_retains_evidence(self):
        for clock in ([0, 20], [0, 0, 10, 20]):
            with self.subTest(attempts=len(clock) - 2):
                server = Mock()
                calls = []
                diagnostics = io.StringIO()

                def on_run(args, calls=calls):
                    calls.append(args)
                    if any(str(arg).endswith("observe.py") for arg in args):
                        self.fail("consumer started after readiness expired")

                def on_exit(output, printed, diagnostics=diagnostics):
                    self.assertFalse((output / "result.json").exists())
                    self.assertEqual(printed.getvalue(), "")
                    self.assertTrue((output / "server.log").is_file())
                    self.assertEqual(len(list(output.glob("*/*.whl"))), 4)
                    workspace = next(output.glob("aethron-installed-*"))
                    self.assertTrue(workspace.is_dir())
                    self.assertIn(str(workspace), diagnostics.getvalue())

                with (
                    redirect_stderr(diagnostics),
                    self.assertRaisesRegex(TimeoutError, "^installed_server_not_ready$"),
                ):
                    self.probe(
                        server=server,
                        on_run=on_run,
                        on_exit=on_exit,
                        vision=True,
                        health_errors=ConnectionRefusedError("synthetic unavailable server"),
                        health_clock=clock,
                    )
                self.assertEqual(server.mock_calls, [call.terminate(), call.wait(timeout=10)])
                self.assertFalse(any(str(arg).endswith("observe.py") for arg in calls[-1]))
                self.assertFalse(
                    any("requirements-vision.lock" in str(arg) for args in calls for arg in args)
                )

    def test_server_readiness_recovers_before_deadline(self):
        from unittest.mock import DEFAULT

        # Two failed probes, then success at 19s; later times drive the existing
        # viewer-independent processing check, without sleeping in this test.
        self.probe(
            health_errors=[ConnectionRefusedError(), TimeoutError(), DEFAULT],
            health_clock=[0, 0, 10, 19, 21, 21],
        )

    def test_server_graceful_shutdown_does_not_force_kill(self):
        server = Mock()
        self.probe(server=server)
        self.assertEqual(server.mock_calls, [call.terminate(), call.wait(timeout=10)])

    def test_server_shutdown_timeout_reaps_without_publishing_success(self):
        for failure in (None, subprocess.CalledProcessError(7, ["observer"]), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                server = Mock()
                expired = subprocess.TimeoutExpired(["server"], 10)
                server.wait.side_effect = [expired, -9]
                self.check_server_shutdown_timeout(server, failure, expired)
                self.assertEqual(
                    server.mock_calls,
                    [call.terminate(), call.wait(timeout=10), call.kill(), call.wait(timeout=10)],
                )

    def check_server_shutdown_timeout(self, server, failure=None, expired=None):
        diagnostics = io.StringIO()
        calls = []

        def on_run(args):
            calls.append(args)
            if failure is not None and any(str(arg).endswith("observe.py") for arg in args):
                raise failure

        def on_exit(output, printed):
            self.assertFalse((output / "result.json").exists())
            self.assertEqual(printed.getvalue(), "")
            self.assertTrue((output / "server.log").is_file())
            self.assertEqual(len(list(output.glob("*/*.whl"))), 4)
            workspace = next(output.glob("aethron-installed-*"))
            self.assertTrue(workspace.is_dir())
            self.assertIn(str(workspace), diagnostics.getvalue())

        with redirect_stderr(diagnostics), self.assertRaises(subprocess.TimeoutExpired) as raised:
            self.probe(server=server, on_run=on_run, on_exit=on_exit, vision=True)
        if expired is not None:
            self.assertIs(raised.exception, expired)
        if failure is not None:
            self.assertIs(raised.exception.__context__, failure)
        self.assertTrue(any(str(arg).endswith("observe.py") for arg in calls[-1]))

    @unittest.skipUnless(os.name == "posix", "SIGTERM-ignore behavior requires POSIX")
    def test_real_unresponsive_server_is_reaped(self):
        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / "ready"
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import signal, sys, time; from pathlib import Path; "
                    "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                    "Path(sys.argv[1]).touch(); time.sleep(60)",
                    str(ready),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists(), "child did not install its signal handler")
                wait = server.wait
                # Exercise real terminate/kill/wait with a short regression budget.
                with patch.object(server, "wait", side_effect=lambda timeout: wait(timeout=0.2)):
                    self.check_server_shutdown_timeout(server)
                self.assertEqual(server.returncode, -signal.SIGKILL, "server was not reaped")
            finally:
                # A failing regression must not itself leave a child behind.
                if server.poll() is None:
                    server.kill()
                server.wait(timeout=5)

    def test_package_timeouts_stop_pipeline_and_retain_evidence(self):
        # Four builds, environment creation, dependency install, wheel install.
        for fail_at in range(1, 8):
            with self.subTest(stage=fail_at):
                self.check_package_timeout(fail_at)

    def test_real_stalled_package_children_are_reaped(self):
        for fail_at in (1, 5, 6, 7):
            with self.subTest(stage=fail_at):
                self.check_package_timeout(fail_at, real_child=True)

    def check_package_timeout(self, fail_at, real_child=False):
        execute, spawn = subprocess.run, subprocess.Popen
        calls, children, failures = [], [], []
        diagnostics = io.StringIO()

        def record_child(*args, **kwargs):
            child = spawn(*args, **kwargs)
            children.append(child)
            return child

        def on_process(args, kwargs):
            calls.append(args)
            if len(calls) != fail_at:
                return
            timeout = kwargs.get("timeout")
            self.assertIsInstance(timeout, (int, float))
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, 180)
            if real_child:
                # Keep the real run/kill/wait behavior, with a short test budget.
                with patch.object(checker.subprocess, "Popen", record_child):
                    try:
                        execute(
                            [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
                            **dict(kwargs, timeout=0.2),
                        )
                    except subprocess.TimeoutExpired as error:
                        failures.append(error)
                        raise
                self.fail("stalled child returned without a timeout")
            failure = subprocess.TimeoutExpired(
                args, timeout, output=b"partial output", stderr=b"diagnostic"
            )
            failures.append(failure)
            raise failure

        def on_exit(output, printed):
            self.assertTrue(output.is_dir())
            self.assertFalse((output / "result.json").exists())
            self.assertEqual(printed.getvalue(), "")
            if fail_at > 1:
                self.assertTrue(list(output.glob("*/*.whl")), "earlier wheels were deleted")
            if fail_at >= 5:
                workspace = Path(calls[4][-1]).parent
                self.assertTrue(workspace.is_dir(), "failed install workspace was deleted")
                self.assertEqual(workspace.parent, output)
                self.assertIn(str(workspace), diagnostics.getvalue())

        with redirect_stderr(diagnostics), self.assertRaises(subprocess.TimeoutExpired) as raised:
            self.probe(on_process=on_process, on_exit=on_exit)
        self.assertEqual(len(calls), fail_at, "no retry or later consumer after expiry")
        self.assertEqual(len(failures), 1)
        self.assertIs(raised.exception, failures[0])
        if real_child:
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].poll(), "timed-out direct child was not reaped")
        else:
            self.assertEqual(raised.exception.output, b"partial output")
            self.assertEqual(raised.exception.stderr, b"diagnostic")

    def test_parent_python_settings_do_not_redirect_venv_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            shadow = Path(directory)
            (shadow / "venv.py").write_text(
                'raise RuntimeError("inherited path redirected venv")\n', encoding="utf-8"
            )
            for variable, value in (
                ("PYTHONHOME", str(shadow / "missing-python-home")),
                ("PYTHONPATH", str(shadow)),
            ):
                with (
                    self.subTest(variable=variable),
                    patch.dict(checker.os.environ, {variable: value}),
                ):
                    calls = []
                    self.probe(real_venv=True, on_run=calls.append)
                    self.assertEqual(checker.os.environ[variable], value)
                    self.assertEqual(sum(call[1:3] == ["-m", "venv"] for call in calls), 1)

    def test_failed_installed_stages_retain_workspace(self):
        stages = {
            "venv": lambda args: args[1:3] == ["-m", "venv"],
            "dependencies": lambda args: "install" in args and "-r" in args,
            "wheels": lambda args: "install" in args and "--no-deps" in args,
            "payload": lambda args: args[-1] == "--installed-edge-payload",
            "console": lambda args: args[1:] == ["--help"],
            "sensor_suite": lambda args: args[-1] == "test_sensor*.py",
            "observer": lambda args: any(str(arg).endswith("observe.py") for arg in args),
            "vision_suite": lambda args: args[-1] == "test*rectification.py",
        }
        for name, matches in stages.items():
            with self.subTest(stage=name):
                self.check_workspace_failure(matches, subprocess.CalledProcessError(7, [name]))

    def test_interrupted_install_retains_workspace(self):
        for failure in (SystemExit(9), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                self.check_workspace_failure(lambda args: "install" in args, failure)

    def check_workspace_failure(self, matches, failure):
        workspaces = []
        diagnostics = io.StringIO()

        def on_run(args):
            if args[1:3] == ["-m", "venv"]:
                work = Path(args[-1]).parent
                workspaces.append(work)
                (work / "partial-evidence").write_bytes(b"retained synthetic evidence")
            if matches(args):
                raise failure

        def on_exit(output, printed):
            self.assertEqual(len(workspaces), 1)
            work = workspaces[0]
            self.assertTrue(work.is_dir(), "failed installed workspace was deleted")
            self.assertEqual(work.parent, output)
            self.assertEqual(
                (work / "partial-evidence").read_bytes(), b"retained synthetic evidence"
            )
            self.assertIn(str(work), diagnostics.getvalue())
            self.assertFalse((output / "result.json").exists())
            self.assertEqual(printed.getvalue(), "")

        with redirect_stderr(diagnostics), self.assertRaises(type(failure)) as raised:
            self.probe(vision=True, on_run=on_run, on_exit=on_exit)
        self.assertIs(raised.exception, failure)

    def test_successful_installed_run_cleans_workspace(self):
        workspaces = []

        def on_run(args):
            if args[1:3] == ["-m", "venv"]:
                workspaces.append(Path(args[-1]).parent)

        def on_exit(output, printed):
            self.assertEqual(len(workspaces), 1)
            self.assertFalse(workspaces[0].exists())
            self.assertTrue((output / "result.json").is_file())
            self.assertIs(json.loads(printed.getvalue())["installed_consumer"], True)

        self.probe(vision=True, on_run=on_run, on_exit=on_exit)

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

    def test_nul_wheel_member_rejects_before_consumers_or_report(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                self.probe(wheel_defect="nul-name", package=package)

    def test_script_destination_rejects_before_consumers_or_report(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                self.probe(wheel_defect="script-destination", package=package)

    def test_undeclared_entry_points_reject_before_consumers_or_report(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                self.probe(wheel_defect="entry-points", package=package)

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

    def test_linked_artifacts_after_consumers_prevent_success_report(self):
        for lane in ("a", "b"):
            with self.subTest(lane=lane):
                self.probe(artifact_change=(lane, "symlink"))

    def test_linked_build_directories_after_consumers_prevent_success_report(self):
        for lane in ("a", "b"):
            with self.subTest(lane=lane):
                self.probe(artifact_change=(lane, "linked_directory"))

    def test_console_failure_prevents_consumer_and_report(self):
        for error in (
            FileNotFoundError("synthetic missing launcher"),
            subprocess.CalledProcessError(2, ["synthetic launcher"]),
            subprocess.TimeoutExpired(["synthetic launcher"], 30),
        ):
            with self.subTest(error=type(error).__name__):
                self.probe(console_error=error)
        self.probe(console_output=" \n")
