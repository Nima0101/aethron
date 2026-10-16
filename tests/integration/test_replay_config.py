"""The offline CLI admits bounded, unambiguous configuration before doing work."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge import cli


class ReplayConfig(unittest.TestCase):
    def invoke(self, path, command="doctor", metadata_error=None):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch("sys.argv", ["aethron-edge", command, "--config", str(path)]),
            patch.object(
                cli.importlib.metadata,
                "version",
                return_value="0.2.0",
                side_effect=metadata_error,
            ),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            try:
                cli.main()
            except SystemExit as exc:
                return exc.code, out.getvalue(), err.getvalue()
            except cli.importlib.metadata.PackageNotFoundError:
                self.fail("doctor leaked an unhandled missing-metadata error")
        return 0, out.getvalue(), err.getvalue()

    def test_malformed_configuration_is_fixed_error(self):
        cases = [
            b"null",
            b"[]",
            b"true",
            b'"private-sentinel"',
            b'{"version":true}',
            b'{"version":1.0}',
            b'{"version":0,"version":1}',
            b'{"version":1,"nested":{"x":0,"x":1}}',
            b'{"version":1,"private-sentinel":NaN}',
            b'{"version":1,"private-sentinel":Infinity}',
            b'{"version":1,"private-sentinel":' + b"[" * 1200 + b"0" + b"]" * 1200 + b"}",
            b'{"version":1}' + b" " * 65536,
            b"\xffprivate-sentinel",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for data in cases:
                with self.subTest(data=data[:64]):
                    path.write_bytes(data)
                    self.assertEqual(self.invoke(path), (2, "", "invalid_request\n"))

    def test_config_read_is_bounded_and_stream_closed(self):
        class Bounded(io.BytesIO):
            def read(self, size=-1):
                if not 0 < size <= 65537:
                    raise AssertionError("unbounded configuration read")
                return super().read(size)

        for length in (65536, 65537):
            with self.subTest(length=length):
                base = b'{"version":1}'
                stream = Bounded(base + b" " * (length - len(base)))
                with patch.object(Path, "open", return_value=stream):
                    code, out, err = self.invoke(Path("config.json"))
                self.assertTrue(stream.closed)
                self.assertEqual(code, 0 if length == 65536 else 2)
                if code == 0:
                    self.assertFalse(json.loads(out)["qualified"])
                    self.assertEqual(err, "")
                else:
                    self.assertEqual((out, err), ("", "invalid_request\n"))

    def test_overflowing_json_numbers_are_fixed_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for number in ("1e309", "-1e309", "9" * 400 + ".0"):
                for value in (number, '[{"nested":' + number + "}]"):
                    with self.subTest(value=value[:64]):
                        path.write_text('{"version":1,"private-sentinel":' + value + "}")
                        self.assertEqual(self.invoke(path), (2, "", "invalid_request\n"))

    def test_finite_extension_numbers_retain_float_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for number in ("1e308", "-1e308", "1.25", "0.0", "1e-300"):
                with self.subTest(number=number):
                    path.write_text('{"version":1,"extension":[' + number + "]}")
                    result = cli._replay_config(path, require_replay=False)["extension"][0]
                    self.assertIs(type(result), float)
                    self.assertEqual(result, float(number))
                    self.assertEqual(self.invoke(path)[0], 0)

    def test_invalid_replay_path_never_opens_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for value in (None, True, 1, [], {}, "", "private\x00sentinel", "\ud800"):
                with self.subTest(value=repr(value)):
                    path.write_text(json.dumps({"version": 1, "replay": value}))
                    with patch.object(Path, "resolve", side_effect=AssertionError("path used")):
                        self.assertEqual(self.invoke(path, "replay"), (2, "", "invalid_request\n"))

    def test_path_resolution_errors_are_private_before_processing(self):
        from aethron_edge import protocol

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"version":1,"replay":"private-sentinel.jsonl"}')
            # Python 3.11/3.12 raise RuntimeError for symlink loops; filesystem
            # failures on newer versions use OSError. Exercise both contracts.
            for error in (RuntimeError("private-sentinel"), OSError("private-sentinel")):
                with (
                    self.subTest(error=type(error).__name__),
                    patch.object(Path, "resolve", side_effect=error),
                    patch.object(protocol, "replay_stream") as replay,
                ):
                    try:
                        result = self.invoke(path, "replay")
                    except RuntimeError:
                        self.fail("path-resolution failure escaped the private CLI boundary")
                    self.assertEqual(result, (2, "", "invalid_request\n"))
                    replay.assert_not_called()

    def test_processing_runtime_errors_are_not_misreported_as_path_errors(self):
        from aethron_edge import protocol

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"version":1,"replay":"fixture.jsonl"}')
            (Path(directory) / "fixture.jsonl").write_bytes(b"")
            with patch.object(
                protocol, "replay_stream", side_effect=RuntimeError("synthetic_processing_error")
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic_processing_error"):
                    self.invoke(path, "replay")

    def test_valid_doctor_does_not_load_model_or_claim_hardware(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"version":1,"replay":"recording.jsonl"}')
            code, out, err = self.invoke(path)
        self.assertEqual((code, err), (0, ""))
        result = json.loads(out)
        self.assertFalse(result["hardware_probed"])
        self.assertFalse(result["qualified"])
        self.assertEqual(result["model"], "not_loaded")
        self.assertEqual(result["core_version"], "0.2.0")

    def test_missing_core_metadata_emits_fixed_failure_without_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"version":1}')
            result = self.invoke(
                path, metadata_error=cli.importlib.metadata.PackageNotFoundError("aethron")
            )
        self.assertEqual(result, (2, "", "doctor_unavailable\n"))

    def test_depth_and_encoding_checked_before_json_allocation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for depth in (8, 9):
                data = b'{"version":1,"extension":' + b"[" * (depth - 1)
                data += b"0" + b"]" * (depth - 1) + b"}"
                path.write_bytes(data)
                if depth == 8:
                    self.assertEqual(self.invoke(path)[0], 0)
                else:
                    with patch.object(
                        cli.json, "loads", side_effect=AssertionError("JSON allocated")
                    ):
                        self.assertEqual(self.invoke(path), (2, "", "invalid_request\n"))
            path.write_bytes('{"version":1}'.encode("utf-16"))
            with patch.object(cli.json, "loads", side_effect=AssertionError("JSON allocated")):
                self.assertEqual(self.invoke(path), (2, "", "invalid_request\n"))


if __name__ == "__main__":
    unittest.main()
