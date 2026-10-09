"""Real SDK signatures with synthetic keys; no configured vehicle or secret."""

import importlib.util
import random
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from pymavlink.dialects.v20 import common


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.telemetry.signing"))
        from aethron_edge.telemetry import signing

        self.api = signing
        self.now = 1_000_000_000
        self.key = bytes(range(32))  # Public synthetic test key, never provisioned.
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "replay.db"
        self.trust = signing.SigningTrust(
            self.key, 7, 10_000_000, self.now, self.now + 60_000_000_000
        )
        signing.provision_replay(self.path, self.trust, system=1, component=1)
        self.source = self.open()
        self.addCleanup(self.source.close)

    def open(self, **changes):
        return self.api.SignedTelemetry(
            1,
            1,
            trust=changes.get("trust", self.trust),
            replay_path=self.path,
            clock=lambda: self.now,
        )

    def packet(self, timestamp=10_000_001, sequence=0, boot=10, link=7, key=None, roll=0.1):
        encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
        encoder.seq = sequence
        encoder.signing.secret_key = self.key if key is None else key
        encoder.signing.sign_outgoing = True
        encoder.signing.link_id = link
        encoder.signing.timestamp = timestamp
        return common.MAVLink_attitude_message(boot, roll, 0, 0, 0, 0, 0).pack(encoder)

    def test_signature_authentication_does_not_upgrade_measurement_evidence(self):
        self.source.ingest(self.packet())
        status = self.source.snapshot()
        self.assertEqual(status.state, "OBSERVED_UNVERIFIED")
        self.assertTrue(status.samples[0].authenticated)
        self.assertEqual(status.samples[0].signature_timestamp, 10_000_001)
        self.assertEqual(status.samples[0].link_id, 7)
        self.assertEqual(status.samples[0].evidence, "external_unverified")
        self.assertIsNone(status.samples[0].capture_ns)
        self.assertFalse(status.perception_eligible)

    def test_replay_rejected_after_restart_and_across_simultaneous_receivers(self):
        packet = self.packet()
        peer = self.open()
        self.addCleanup(peer.close)
        self.source.ingest(packet)
        peer.ingest(packet)
        self.assertEqual(peer.snapshot().reason, "signature_replay")
        self.source.close()
        restarted = self.open()
        self.addCleanup(restarted.close)
        restarted.ingest(packet)
        self.assertEqual(restarted.snapshot().reason, "signature_replay")
        restarted.ingest(self.packet(timestamp=10_000_002, sequence=1, boot=11))
        self.assertTrue(restarted.snapshot().samples[0].authenticated)

    def test_concurrent_receivers_commit_one_counter_before_publication(self):
        peer = self.open()
        self.addCleanup(peer.close)
        barrier = threading.Barrier(2)

        def receive(source):
            barrier.wait(timeout=1)
            source.ingest(self.packet())
            return source.snapshot()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(receive, (self.source, peer)))
        self.assertEqual(sum(bool(status.samples) for status in statuses), 1)
        rejected = next(status for status in statuses if not status.samples)
        self.assertIn(rejected.reason, ("signature_replay", "replay_store_failed"))

    def test_installed_fresh_process_rejects_previously_committed_packet(self):
        packet = self.packet()
        self.source.ingest(packet)
        self.source.close()
        program = """
import sys
from pathlib import Path
from aethron_edge.telemetry.signing import SigningTrust, SignedTelemetry
trust = SigningTrust(bytes(range(32)), 7, 10_000_000, 1_000_000_000, 61_000_000_000)
source = SignedTelemetry(1, 1, trust=trust, replay_path=Path(sys.argv[1]),
                         clock=lambda: 1_000_000_000)
source.ingest(bytes.fromhex(sys.argv[2]))
assert source.snapshot().reason == 'signature_replay'
source.ingest(bytes.fromhex(sys.argv[3]))
assert source.snapshot().samples[0].authenticated
source.close()
print('fresh_process_replay_rejected')
"""
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                program,
                str(self.path),
                packet.hex(),
                self.packet(timestamp=10_000_002, sequence=1, boot=11).hex(),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "fresh_process_replay_rejected")

    def test_forged_higher_timestamp_cannot_poison_replay_state(self):
        forged = self.packet(timestamp=15_000_000, key=bytes(reversed(range(32))))
        self.source.ingest(forged)
        self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        self.source.ingest(self.packet())
        self.assertTrue(self.source.snapshot().samples[0].authenticated)

    def test_signature_tampering_unsigned_downgrade_and_other_link_are_rejected(self):
        tampered = bytearray(self.packet())
        tampered[-1] ^= 1
        unsigned = common.MAVLink_attitude_message(10, 0, 0, 0, 0, 0, 0).pack(common.MAVLink(None))
        for packet in (bytes(tampered), unsigned, self.packet(link=8), self.packet()[:-1]):
            with self.subTest(length=len(packet)):
                self.source.ingest(packet)
                self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        self.source.ingest(self.packet())
        self.assertTrue(self.source.snapshot().samples[0].authenticated)

    def test_invalid_payload_does_not_consume_signature_counter(self):
        self.source.ingest(self.packet(roll=float("nan")))
        self.assertEqual(self.source.snapshot().reason, "invalid_values")
        self.source.ingest(self.packet())
        self.assertTrue(self.source.snapshot().samples[0].authenticated)

    def test_floor_stale_and_future_timestamps_fail_closed(self):
        for timestamp in (10_000_000, 1, 16_000_001):
            self.source.ingest(self.packet(timestamp=timestamp))
            self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        self.now += 60_000_000_000 - 1
        # Floor+1 has become almost 60s old, still inside signature's 60s window.
        self.source.ingest(self.packet())
        self.assertTrue(self.source.snapshot().samples[0].authenticated)

    def test_expiry_withdraws_without_traffic_and_cannot_recover(self):
        self.now = self.trust.valid_until_ns - 1
        self.source.ingest(self.packet(timestamp=15_999_999))
        self.assertTrue(self.source.snapshot().samples[0].authenticated)
        self.now += 1
        self.assertEqual(self.source.snapshot().reason, "signing_authority_expired")
        self.source.ingest(self.packet(timestamp=16_000_000, sequence=1, boot=11))
        self.assertEqual(self.source.snapshot().samples, ())

    def test_clock_rollback_and_not_yet_valid_authority(self):
        self.now -= 1
        self.source.ingest(self.packet())
        self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        self.now += 1
        self.source.ingest(self.packet())
        self.assertEqual(self.source.snapshot().state, "UNKNOWN")

    def test_journal_missing_replaced_or_write_failure_does_not_publish(self):
        self.path.unlink()
        self.source.ingest(self.packet())
        self.assertEqual(self.source.snapshot().reason, "replay_store_failed")
        self.assertEqual(self.source.snapshot().samples, ())
        with self.assertRaisesRegex(ValueError, "invalid_replay_store"):
            self.open()

    def test_locked_journal_fails_closed_before_observation(self):
        blocker = sqlite3.connect(self.path)
        self.addCleanup(blocker.close)
        blocker.execute("BEGIN IMMEDIATE")
        self.source.ingest(self.packet())
        self.assertEqual(self.source.snapshot().reason, "replay_store_failed")
        blocker.rollback()
        self.source.ingest(self.packet())
        self.assertEqual(self.source.snapshot().samples, ())

    def test_failed_connection_setup_closes_database(self):
        self.path.write_bytes(b"not a SQLite database")
        opened = []
        connect = sqlite3.connect

        def record_connection(*args, **kwargs):
            connection = connect(*args, **kwargs)
            opened.append(connection)
            self.addCleanup(connection.close)
            return connection

        with patch.object(self.api.sqlite3, "connect", side_effect=record_connection):
            with self.assertRaisesRegex(ValueError, "invalid_replay_store"):
                self.open()
        self.assertEqual(len(opened), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute("SELECT 1")

    def test_journal_replacement_links_permissions_and_corruption_are_rejected(self):
        original = self.path.with_suffix(".original")
        self.path.rename(original)
        self.path.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "invalid_replay_store"):
            self.open()
        self.path.unlink()
        self.path.write_bytes(original.read_bytes())
        self.path.chmod(0o600)
        self.source.ingest(self.packet())
        self.assertEqual(self.source.snapshot().reason, "replay_store_failed")
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "invalid_replay_store"):
            self.open()
        self.path.chmod(0o600)
        self.path.write_bytes(b"invalid sqlite")
        with self.assertRaisesRegex(ValueError, "invalid_replay_store"):
            self.open()

    def test_old_signature_expires_even_for_an_established_stream(self):
        self.source.close()
        trust = self.api.SigningTrust(self.key, 7, 10_000_000, self.now, self.now + 120_000_000_000)
        source = self.open(trust=trust)
        self.addCleanup(source.close)
        source.ingest(self.packet())
        self.now += 60_000_030_000
        source.ingest(self.packet(timestamp=10_000_002, sequence=1, boot=11))
        self.assertEqual(source.snapshot().reason, "signature_time_or_link")

    def test_signed_loopback_and_tampering_campaign_never_transmit_or_poison(self):
        from aethron_edge.telemetry.mavlink import UdpTelemetry

        rng = random.Random(16032)
        packet = self.packet(timestamp=15_000_000)
        for _ in range(2000):
            changed = bytearray(packet)
            changed[rng.randrange(len(changed))] ^= rng.randrange(1, 256)
            self.source.ingest(bytes(changed))
            self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        with (
            UdpTelemetry(self.source, port=0) as receiver,
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender,
        ):
            sender.bind(("127.0.0.1", 0))
            sender.settimeout(0.02)
            sender.sendto(self.packet(), ("127.0.0.1", receiver.port))
            self.assertTrue(receiver.poll().samples[0].authenticated)
            with self.assertRaises(socket.timeout):
                sender.recvfrom(1)

    def test_journal_is_bound_to_key_and_stream_and_cannot_be_reprovisioned(self):
        other = self.api.SigningTrust(
            bytes(reversed(range(32))), 7, 10_000_000, self.now, self.now + 60_000_000_000
        )
        with self.assertRaisesRegex(ValueError, "invalid_replay_store"):
            self.open(trust=other)
        with self.assertRaises(FileExistsError):
            self.api.provision_replay(self.path, self.trust, system=1, component=1)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_invalid_trust_is_rejected_and_key_is_not_in_repr(self):
        self.assertNotIn(repr(self.key), repr(self.trust))
        cases = (
            (bytes(31), 7, 10, 1, 2),
            (self.key, True, 10, 1, 2),
            (self.key, 7, -1, 1, 2),
            (self.key, 7, 2**48, 1, 2),
            (self.key, 7, 10, 2, 2),
            (self.key, 7, 10, True, 2),
        )
        for args in cases:
            with self.subTest(args=args[1:]), self.assertRaises(ValueError):
                self.api.SigningTrust(*args)


if __name__ == "__main__":
    unittest.main()
