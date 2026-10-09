"""Synthetic MAVLink wire batches; no autopilot or physical timing claim."""

import importlib.util
import random
import socket
import tempfile
import unittest
from pathlib import Path

from aethron_edge.telemetry.mavlink import PassiveTelemetry
from aethron_edge.telemetry.signing import SignedTelemetry, SigningTrust, provision_replay
from pymavlink.dialects.v20 import common


def packet(seq=0, boot=10, *, kind="attitude", signed=False):
    encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
    encoder.seq = seq
    if signed:
        encoder.signing.secret_key = bytes(range(32))  # Public synthetic fixture key.
        encoder.signing.sign_outgoing = True
        encoder.signing.link_id = 7
        encoder.signing.timestamp = 10_000_001 + seq
    if kind == "position":
        message = common.MAVLink_local_position_ned_message(boot, 1, 2, 3, 4, 5, 6)
    elif kind == "heartbeat":
        message = common.MAVLink_heartbeat_message(0, 0, 0, 0, 0, 3)
    else:
        message = common.MAVLink_attitude_message(boot, 0.1, 0, 0, 0, 0, 0)
    return message.pack(encoder)


class DatagramTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.telemetry.datagram_v1"))
        from aethron_edge.telemetry.datagram_v1 import DatagramTelemetryV1, UdpTelemetryV1

        self.api, self.udp = DatagramTelemetryV1, UdpTelemetryV1
        self.now = 1_000_000_000
        self.source = PassiveTelemetry(1, 1, clock=lambda: self.now)
        self.receiver = self.api(self.source, clock=lambda: self.now)
        self.addCleanup(self.receiver.close)

    def test_two_messages_keep_units_and_unverified_provenance(self):
        self.receiver.ingest(packet() + packet(1, kind="position"))
        status = self.receiver.snapshot()
        self.assertEqual(status.state, "OBSERVED_UNVERIFIED")
        self.assertEqual([s.message for s in status.samples], ["ATTITUDE", "LOCAL_POSITION_NED"])
        self.assertEqual([s.units[0] for s in status.samples], ["rad", "m"])
        self.assertFalse(status.perception_eligible)
        for sample in status.samples:
            self.assertEqual(sample.evidence, "external_unverified")
            self.assertIsNone(sample.capture_ns)
            self.assertFalse(sample.authenticated)

    def test_exact_packet_limit_and_overflow_withdraw(self):
        self.receiver.ingest(b"".join(packet(i, 10 + i) for i in range(16)))
        self.assertEqual(self.receiver.snapshot().samples[0].source_boot_ms, 25)
        self.receiver.ingest(b"".join(packet(i, 10 + i) for i in range(16, 33)))
        self.assertEqual(self.receiver.snapshot().state, "UNKNOWN")
        # Framing/count rejection must not consume the valid prefix's sequence.
        self.receiver.ingest(packet(16, 26))
        self.assertEqual(self.receiver.snapshot().samples[0].source_boot_ms, 26)

    def test_trailing_corruption_is_rejected_before_consuming_prefix(self):
        for suffix in (b"x", b"\xfd", packet(1)[:-1], b"\xfe" + packet(1)[1:]):
            with self.subTest(suffix=suffix[:2]):
                source = PassiveTelemetry(1, 1, clock=lambda: self.now)
                receiver = self.api(source, clock=lambda: self.now)
                self.addCleanup(receiver.close)
                receiver.ingest(packet() + suffix)
                self.assertEqual(receiver.snapshot().state, "UNKNOWN")
                receiver.ingest(packet())
                self.assertEqual(receiver.snapshot().state, "OBSERVED_UNVERIFIED")

    def test_rejected_middle_packet_cannot_be_hidden_by_valid_tail(self):
        corrupt = bytearray(packet(1, 11))
        corrupt[-1] ^= 1
        for middle in (bytes(corrupt), packet(1, kind="heartbeat"), packet(0, 11)):
            source = PassiveTelemetry(1, 1, clock=lambda: self.now)
            receiver = self.api(source, clock=lambda: self.now)
            self.addCleanup(receiver.close)
            receiver.ingest(packet() + middle + packet(2, 12))
            self.assertEqual(receiver.snapshot().state, "UNKNOWN")
            self.assertEqual(receiver.snapshot().samples, ())
            receiver.ingest(packet(2, 12))
            self.assertEqual(receiver.snapshot().state, "OBSERVED_UNVERIFIED")

    def test_rejection_reason_survives_silence(self):
        self.receiver.ingest(packet() + packet(1, kind="heartbeat"))
        self.assertEqual(self.receiver.snapshot().reason, "unsupported_message")
        self.now += 100_000_001
        self.assertEqual(self.receiver.snapshot().reason, "unsupported_message")

    def test_unknown_flags_reject_entire_batch_before_decoding(self):
        for index, value in ((2, 2), (2, 3), (3, 1)):
            source = PassiveTelemetry(1, 1, clock=lambda: self.now)
            receiver = self.api(source, clock=lambda: self.now)
            self.addCleanup(receiver.close)
            invalid = bytearray(packet(1, 11))
            invalid[index] = value
            receiver.ingest(packet() + bytes(invalid))
            self.assertEqual(receiver.snapshot().state, "UNKNOWN")
            receiver.ingest(packet())
            self.assertEqual(receiver.snapshot().state, "OBSERVED_UNVERIFIED")

    def test_invalid_inputs_clear_previous_samples_without_echo(self):
        for value in (b"", None, bytearray(packet()), b"secret" * 1000):
            source = PassiveTelemetry(1, 1, clock=lambda: self.now)
            receiver = self.api(source, clock=lambda: self.now)
            self.addCleanup(receiver.close)
            receiver.ingest(packet())
            self.assertEqual(receiver.snapshot().state, "OBSERVED_UNVERIFIED")
            receiver.ingest(value)
            status = receiver.snapshot()
            self.assertEqual(status.state, "UNKNOWN")
            self.assertEqual(status.samples, ())
            self.assertNotIn("secret", repr(status))

    def test_receipt_deadline_includes_decode_time(self):
        class SlowDecoder(PassiveTelemetry):
            def ingest(source, data):
                self.now += 60_000_000
                super().ingest(data)

        source = SlowDecoder(1, 1, clock=lambda: self.now)
        receiver = self.api(source, clock=lambda: self.now)
        self.addCleanup(receiver.close)
        receiver.ingest(packet() + packet(1, kind="position"))
        self.assertEqual(receiver.snapshot().state, "UNKNOWN")

    def test_new_batch_cannot_extend_previous_batch_receipt_deadline(self):
        class SlowDecoder(PassiveTelemetry):
            def ingest(source, data):
                if data:
                    self.now += 40_000_000
                super().ingest(data)

        source = SlowDecoder(1, 1, clock=lambda: self.now)
        receiver = self.api(source, clock=lambda: self.now)
        self.addCleanup(receiver.close)
        receiver.ingest(packet())
        self.now += 20_000_000
        receiver.ingest(packet(1, kind="position"))
        self.now += 1
        status = receiver.snapshot()
        self.assertEqual([s.message for s in status.samples], ["LOCAL_POSITION_NED"])

    def test_invalid_clocks_latch_even_if_later_corrected(self):
        for invalid in (True, -1, 1.0, None):
            source = PassiveTelemetry(1, 1, clock=lambda: 1_000_000_000)
            receiver = self.api(source, clock=lambda: self.now)
            self.addCleanup(receiver.close)
            self.now = invalid
            receiver.ingest(packet())
            self.assertEqual(receiver.snapshot().reason, "local_clock_invalid")
            self.now = 1_000_000_000
            receiver.ingest(packet())
            self.assertEqual(receiver.snapshot().state, "UNKNOWN")

    def test_invalid_sources_and_ports_do_not_open_socket(self):
        with self.assertRaisesRegex(ValueError, "invalid_telemetry_source"):
            self.api(object())
        with self.assertRaisesRegex(ValueError, "invalid_datagram_source"):
            self.udp(self.source, port=0)
        for invalid in (True, -1, 65536, 1.0, None):
            with self.assertRaisesRegex(ValueError, "invalid_port"):
                self.udp(self.receiver, port=invalid)

    def test_expiry_without_traffic_and_clock_rollback_latch(self):
        self.receiver.ingest(packet())
        self.now += 100_000_000
        self.assertEqual(self.receiver.snapshot().state, "OBSERVED_UNVERIFIED")
        self.now += 1
        self.assertEqual(self.receiver.snapshot().state, "UNKNOWN")
        self.now -= 1
        self.receiver.snapshot()
        self.now += 1
        self.receiver.ingest(packet(1, 11))
        self.assertEqual(self.receiver.snapshot().state, "UNKNOWN")

    def test_signed_batch_and_rejected_downgrade_keep_replay_counter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.db"
            trust = SigningTrust(bytes(range(32)), 7, 10_000_000, self.now, self.now + 10**9)
            provision_replay(path, trust, system=1, component=1)
            source = SignedTelemetry(1, 1, trust=trust, replay_path=path, clock=lambda: self.now)
            receiver = self.api(source, clock=lambda: self.now)
            self.addCleanup(receiver.close)
            receiver.ingest(packet(signed=True) + packet(1, 11, signed=True))
            self.assertTrue(receiver.snapshot().samples[0].authenticated)
            receiver.ingest(packet(2, 12, signed=True) + packet(3, 13))
            self.assertEqual(receiver.snapshot().state, "UNKNOWN")
            receiver.close()
            source = SignedTelemetry(1, 1, trust=trust, replay_path=path, clock=lambda: self.now)
            receiver = self.api(source, clock=lambda: self.now)
            self.addCleanup(receiver.close)
            receiver.ingest(packet(2, 12, signed=True))
            self.assertEqual(receiver.snapshot().reason, "signature_replay")
            receiver.ingest(packet(3, 13, signed=True))
            self.assertEqual(receiver.snapshot().samples[0].source_boot_ms, 13)

    def test_loopback_batch_silence_oversize_and_no_outbound_packet(self):
        with self.udp(self.receiver, port=0) as receiver:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.bind(("127.0.0.1", 0))
                sender.settimeout(0.02)
                sender.sendto(packet() + packet(1, kind="position"), ("127.0.0.1", receiver.port))
                self.assertEqual(len(receiver.poll().samples), 2)
                with self.assertRaises(socket.timeout):
                    sender.recvfrom(1)
                self.now += 100_000_001
                self.assertEqual(receiver.poll().state, "UNKNOWN")
                sender.sendto(b"x" * 5000, ("127.0.0.1", receiver.port))
                self.assertEqual(receiver.poll().state, "UNKNOWN")
        self.receiver.ingest(packet(2, 12))
        self.assertEqual(self.receiver.snapshot().reason, "closed")

    def test_bounded_invalid_wire_never_produces_samples(self):
        rng = random.Random(3101)
        for _ in range(128):
            self.receiver.ingest(packet() + rng.randbytes(rng.randrange(1, 100)))
            self.assertEqual(self.receiver.snapshot().state, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
