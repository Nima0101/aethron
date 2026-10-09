"""Offline process lifecycle with synthetic signed wire traffic, no hardware."""

import importlib.util
import socket
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from aethron_edge.telemetry.signing import SigningTrust, provision_replay
from pymavlink.dialects.v20 import common


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.telemetry.worker"))
        from aethron_edge.telemetry.worker import TelemetryProfile, TelemetrySupervisor

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "replay.db"
        self.key = bytes(range(32))
        self.issued = time.monotonic_ns()
        self.trust = SigningTrust(
            self.key, 7, 10_000_000, self.issued, self.issued + 60_000_000_000
        )
        provision_replay(self.path, self.trust, system=1, component=1)
        self.profile = TelemetryProfile(1, 1, 0, str(self.path))
        self.supervisor = TelemetrySupervisor(self.profile, self.trust)
        self.addCleanup(self.supervisor.close)
        self.sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sender.bind(("127.0.0.1", 0))
        self.sender.settimeout(0.02)
        self.addCleanup(self.sender.close)
        self.sequence = 0

    def wait(self, predicate, limit=10):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            status = self.supervisor.snapshot()
            if predicate(status):
                return status
            time.sleep(0.005)
        self.fail(f"telemetry_deadline: {self.supervisor.snapshot()}")

    def start(self):
        self.supervisor.start()
        return self.wait(lambda s: s["state"] == "waiting")

    def packet(self, *, timestamp=10_000_001, boot=10, sequence=0):
        encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
        encoder.seq = sequence
        encoder.signing.secret_key = self.key
        encoder.signing.sign_outgoing = True
        encoder.signing.timestamp = timestamp
        encoder.signing.link_id = 7
        return common.MAVLink_attitude_message(boot, 0.1, 0.2, 0.3, 0, 0, 0).pack(encoder)

    def send(self, port, **fields):
        self.sender.sendto(self.packet(**fields), ("127.0.0.1", port))

    def observe(self, port):
        # Exercise an actual periodic telemetry stream. A single packet may
        # expire on a loaded host; those measured negatives are retained.
        deadline = time.monotonic() + 10
        next_send = 0
        while time.monotonic() < deadline:
            status = self.supervisor.snapshot()
            if status["authenticated"]:
                return status
            if time.monotonic() >= next_send:
                self.send(
                    port,
                    timestamp=10_000_001 + self.sequence,
                    sequence=self.sequence % 256,
                    boot=10 + self.sequence,
                )
                self.sequence += 1
                next_send = time.monotonic() + 0.05
            time.sleep(0.005)
        self.fail(f"stream_deadline: {self.supervisor.snapshot()}")

    def test_start_capture_silence_and_close_without_any_viewer(self):
        status = self.start()
        observed = self.observe(status["port"])
        self.assertTrue(observed["authenticated"])
        self.assertFalse(observed["perception_eligible"])
        self.assertEqual(observed["samples"], 1)
        self.assertNotIn("values", observed)
        self.assertNotIn(str(self.path), repr(observed))
        self.assertNotIn(repr(self.key), repr(observed))
        self.wait(lambda s: s["state"] == "waiting", limit=1)
        with self.assertRaises(socket.timeout):
            self.sender.recvfrom(1)
        process = self.supervisor.process
        self.supervisor.close()
        self.assertFalse(process.is_alive())
        self.assertEqual(self.supervisor.snapshot()["state"], "stopped")

    def test_crash_restart_reuses_grant_and_replay_journal(self):
        status = self.start()
        self.observe(status["port"])
        original = self.supervisor.process
        original.kill()
        original.join(timeout=2)
        self.assertFalse(self.supervisor.snapshot()["authenticated"])
        recovered = self.wait(lambda s: s["restarts"] == 1 and s["state"] == "waiting")
        with closing(sqlite3.connect(self.path)) as connection:
            accepted = connection.execute("SELECT timestamp FROM replay").fetchone()[0]
        self.send(recovered["port"], timestamp=accepted)
        time.sleep(0.05)
        self.assertFalse(self.supervisor.snapshot()["authenticated"])
        self.observe(recovered["port"])
        self.assertIs(self.supervisor.trust, self.trust)

    def test_missing_journal_is_latched_not_recreated(self):
        self.path.unlink()
        self.supervisor.start()
        status = self.wait(lambda s: s["state"] == "fault")
        self.assertEqual(status["reason"], "worker_fault")
        self.assertFalse(self.path.exists())
        self.assertEqual(status["restarts"], 0)

    def test_expired_grant_cannot_be_reissued_by_start_or_recovery(self):
        from aethron_edge.telemetry.worker import TelemetrySupervisor

        self.supervisor.close()
        old = time.monotonic_ns() - 10_000
        trust = SigningTrust(self.key, 7, 10_000_000, old - 1000, old)
        self.supervisor = TelemetrySupervisor(self.profile, trust)
        self.addCleanup(self.supervisor.close)
        self.supervisor.start()
        self.assertEqual(self.supervisor.snapshot()["reason"], "authority_expired")
        self.assertIsNone(self.supervisor.process)

    def test_parent_expires_worker_message_independently(self):
        status = self.start()
        self.observe(status["port"])
        # Freeze child to exercise the parent's freshness guard without relying
        # on a worker publication. Resume in finally; only our own child is touched.
        import os
        import signal

        child = self.supervisor.process
        os.kill(child.pid, signal.SIGSTOP)
        try:
            self.wait(lambda s: not s["authenticated"], limit=1)
            self.assertFalse(self.supervisor.snapshot()["perception_eligible"])
        finally:
            os.kill(child.pid, signal.SIGCONT)


class WorkerClockTests(unittest.TestCase):
    def runtime(self):
        from aethron_edge.telemetry.worker import TelemetryProfile, TelemetrySupervisor

        return TelemetrySupervisor(
            TelemetryProfile(1, 1, 0, "unused"), SigningTrust(bytes(32), 1, 100, 1, 2000)
        )

    def test_snapshot_does_not_compare_against_later_concurrent_clock_sample(self):
        supervisor = self.runtime()
        supervisor._last_now = 100

        def concurrent_clock():
            supervisor._last_now = 102
            return 101

        with patch("aethron_edge.telemetry.worker.time.monotonic_ns", concurrent_clock):
            self.assertEqual(supervisor.snapshot()["state"], "starting")

    def test_message_freshness_uses_time_after_mailbox_read(self):
        supervisor = self.runtime()
        supervisor._started_ns = 1
        supervisor._channel = Mock()
        supervisor._channel.get_nowait.return_value = {
            "state": "waiting",
            "port": 1234,
            "samples": 0,
            "expires_ns": 0,
            "emitted_ns": 101,
            "source_reason": "no_observation",
            "max_poll_ms": 0,
            "max_decode_ms": 0,
            "max_commit_ms": 0,
        }
        with patch("aethron_edge.telemetry.worker.time.monotonic_ns", return_value=102):
            supervisor._consume(100)
        self.assertIsNone(supervisor._fault)

    def test_unstarted_process_can_be_retired_after_spawn_failure(self):
        import multiprocessing as mp

        from aethron_edge.mailbox import StopToken

        supervisor = self.runtime()
        context = mp.get_context("spawn")
        supervisor.process = context.Process(target=time.sleep, args=(0,))
        supervisor._child_stop = StopToken(context)
        supervisor._retire()
        self.assertIsNone(supervisor.process)


if __name__ == "__main__":
    unittest.main()
