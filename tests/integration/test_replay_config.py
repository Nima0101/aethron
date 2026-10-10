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
    def invoke(self, path, command="doctor"):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch("sys.argv", ["aethron-edge", command, "--config", str(path)]),
            patch.object(cli.importlib.metadata, "version", return_value="0.2.0"),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            try:
                cli.main()
            except SystemExit as exc:
                return exc.code, out.getvalue(), err.getvalue()
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

    def test_invalid_replay_path_never_opens_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for value in (None, True, 1, [], {}, "", "private\x00sentinel", "\ud800"):
                with self.subTest(value=repr(value)):
                    path.write_text(json.dumps({"version": 1, "replay": value}))
                    with patch.object(Path, "resolve", side_effect=AssertionError("path used")):
                        self.assertEqual(self.invoke(path, "replay"), (2, "", "invalid_request\n"))

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
