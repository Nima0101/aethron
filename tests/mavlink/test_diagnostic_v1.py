"""Finite subprocess diagnostics with synthetic localhost packets only."""

import io
import json
import select
import socket
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from test_datagram_v1 import packet

MODULE = "aethron_edge.telemetry.diagnostic_v1"


class DiagnosticTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", MODULE, *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_silence_is_unknown_and_normal_exit_closes(self):
        result = self.run_cli("--port", "0", "--duration-ms", "40")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(rows[0]["event"], "listening")
        self.assertGreater(rows[0]["port"], 0)
        self.assertEqual(rows[-1]["reason"], "closed")
        self.assertTrue(all(row["state"] == "UNKNOWN" for row in rows[1:]))
        self.assertTrue(all(row["sample_count"] == 0 for row in rows[1:]))

    def test_real_batch_malformed_withdrawal_and_no_payload_or_response(self):
        process = subprocess.Popen(
            [sys.executable, "-m", MODULE, "--port", "0", "--duration-ms", "400"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        try:
            self.assertTrue(select.select([process.stdout], [], [], 10)[0])
            first = process.stdout.readline()
            if not first:
                self.fail(process.stderr.read().decode())
            ready = json.loads(first)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.bind(("127.0.0.1", 0))
                sender.settimeout(0.02)
                address = ("127.0.0.1", ready["port"])
                sender.sendto(packet() + packet(1, kind="position"), address)
                sender.sendto(b"private-payload", address)
                sender.sendto(packet(2, 12, signed=True), address)
                with self.assertRaises(socket.timeout):
                    sender.recvfrom(1)
                stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr.decode())
            rows = [json.loads(line) for line in stdout.splitlines()]
            observed = [row for row in rows if row["state"] == "OBSERVED_UNVERIFIED"]
            self.assertTrue(observed)
            self.assertEqual(observed[0]["sample_count"], 2)
            self.assertTrue(any(row["reason"] == "invalid_datagram" for row in rows))
            self.assertTrue(any(row["reason"] == "unsupported_packet" for row in rows))
            self.assertEqual(rows[-1]["reason"], "closed")
            allowed = {
                "version",
                "event",
                "state",
                "reason",
                "sample_count",
                "authenticated",
                "evidence",
                "perception_eligible",
            }
            for row in rows:
                self.assertEqual(set(row), allowed)
                self.assertEqual(row["evidence"], "external_unverified")
                self.assertFalse(row["authenticated"])
                self.assertFalse(row["perception_eligible"])
            self.assertNotIn(b"private-payload", stdout + stderr)
            self.assertLessEqual(len(rows), 1501)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)

    def test_duration_sender_and_port_bounds_fail_before_listening(self):
        for args in (
            ["--duration-ms", "0", "--port", "0"],
            ["--duration-ms", "30001", "--port", "0"],
            ["--duration-ms", "1", "--port", "65536"],
            ["--duration-ms", "1", "--port", "0", "--system-id", "0"],
            ["--duration-ms", "1", "--port", "0", "--component-id", "256"],
        ):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)

    def test_occupied_port_has_fixed_error_without_details(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as held:
            held.bind(("127.0.0.1", 0))
            result = self.run_cli("--port", str(held.getsockname()[1]), "--duration-ms", "1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "telemetry_diagnostic_failed\n")

    def test_poll_budget_stops_even_when_duration_clock_stalls(self):
        from aethron_edge.telemetry import diagnostic_v1

        class FloodReceiver:
            def __init__(self, source, *, port):
                self.source, self.port, self.polls = source, port, 0

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.source.close()

            def poll(self):
                self.polls += 1
                if self.polls > 1500:
                    raise AssertionError("unbounded_polling")
                return self.source.snapshot()

        output = io.StringIO()
        with (
            patch.object(diagnostic_v1, "UdpTelemetryV1", FloodReceiver),
            patch.object(diagnostic_v1.time, "monotonic_ns", return_value=0),
            redirect_stdout(output),
        ):
            result = diagnostic_v1.main(["--port", "0", "--duration-ms", "30000"])
        self.assertEqual(result, 0)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(rows), 1502)
        self.assertEqual(rows[-1]["reason"], "closed")


if __name__ == "__main__":
    unittest.main()
