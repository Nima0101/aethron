"""Provenance failures must invalidate an earlier evaluation success."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from scripts import temporal_evaluate as temporal


class TemporalProvenanceFailure(unittest.TestCase):
    def test_windows_source_names_are_portable_in_success_and_failure_reports(self):
        for passed in (True, False):
            with self.subTest(passed=passed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sources = {
                    "aethron/example.py": b"value = 1\n",
                    "aethron/nested/example.py": b"value = 2\n",
                }
                for name, payload in sources.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
                original_relative = Path.relative_to

                def windows_relative(
                    path, *args, original_relative=original_relative, root=root, sources=sources
                ):
                    relative = original_relative(path, *args)
                    if args == (root,) and relative.as_posix() in sources:
                        return PureWindowsPath(*relative.parts)
                    return relative

                outdir = root / "output"
                with (
                    patch.object(temporal, "ROOT", root),
                    patch.object(Path, "relative_to", windows_relative),
                    patch.object(temporal, "synthetic_fixture_paths", return_value=[]),
                    patch.object(temporal, "benchmark", return_value={"passed": passed}),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    if passed:
                        temporal.run(outdir, include_recorded=False)
                    else:
                        with self.assertRaises(AssertionError):
                            temporal.run(outdir, include_recorded=False)
                reports = list(outdir.glob("*.json"))
                self.assertEqual(len(reports), 1 if passed else 2)
                for report_path in reports:
                    report = json.loads(report_path.read_bytes())
                    self.assertIs(report["passed"], passed)
                    self.assertEqual(
                        report["runtime_sha256"],
                        {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()},
                    )

    def test_metadata_failure_replaces_stale_success_and_propagates(self):
        for stage in ("runtime", "script", "python", "platform"):
            for error_type in (OSError, KeyboardInterrupt):
                with self.subTest(stage=stage, error=error_type.__name__):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        source = root / "aethron/example.py"
                        source.parent.mkdir()
                        source.write_text("value = 1\n", encoding="utf-8")
                        outdir = root / "output"
                        outdir.mkdir()
                        report_path = outdir / "temporal-evaluation.json"
                        report_path.write_text('{"passed": true, "stale": true}')
                        error = error_type("private_metadata_error")
                        original_read = Path.read_bytes
                        failed_path = source if stage == "runtime" else Path(temporal.__file__)

                        def read(
                            path,
                            stage=stage,
                            failed_path=failed_path,
                            error=error,
                            original_read=original_read,
                        ):
                            if stage in ("runtime", "script") and path == failed_path:
                                raise error
                            return original_read(path)

                        with contextlib.ExitStack() as stack:
                            stack.enter_context(patch.object(temporal, "ROOT", root))
                            stack.enter_context(patch.object(Path, "read_bytes", read))
                            if stage in ("python", "platform"):
                                function = "python_version" if stage == "python" else "system"
                                stack.enter_context(
                                    patch.object(temporal.platform, function, side_effect=error)
                                )
                            fixtures = stack.enter_context(
                                patch.object(temporal, "synthetic_fixture_paths")
                            )
                            benchmark = stack.enter_context(patch.object(temporal, "benchmark"))
                            recorded = stack.enter_context(patch.object(temporal, "recorded"))
                            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                            with self.assertRaises(error_type) as caught:
                                temporal.run(outdir)
                        self.assertIs(caught.exception, error)
                        fixtures.assert_not_called()
                        benchmark.assert_not_called()
                        recorded.assert_not_called()
                        self.assertEqual(output.getvalue(), "")
                        report = json.loads(report_path.read_text())
                        self.assertIs(report["passed"], False)
                        self.assertEqual(report["failure_stage"], "provenance")
                        self.assertEqual(report["synthetic"], {})
                        self.assertNotIn("stale", report)
                        self.assertNotIn("private_metadata_error", report_path.read_text())

    def test_success_retains_source_and_environment_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "aethron/example.py"
            source.parent.mkdir()
            source.write_bytes(b"value = 1\n")
            with (
                patch.object(temporal, "ROOT", root),
                patch.object(temporal, "synthetic_fixture_paths", return_value=[]),
                patch.object(temporal, "benchmark", return_value={"passed": True}),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                report = temporal.run(root / "output", include_recorded=False)
            self.assertIs(report["passed"], True)
            self.assertNotIn("failure_stage", report)
            self.assertEqual(
                report["runtime_sha256"],
                {"aethron/example.py": hashlib.sha256(source.read_bytes()).hexdigest()},
            )
            self.assertEqual(
                report["evaluation_script_sha256"],
                hashlib.sha256(Path(temporal.__file__).read_bytes()).hexdigest(),
            )
            self.assertEqual(report["python"], temporal.platform.python_version())
            self.assertEqual(
                report["platform"], temporal.platform.system() + " " + temporal.platform.machine()
            )
