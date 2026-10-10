"""Optional SDK lane: synthetic real wire packets, no hardware qualification."""

import asyncio
import math
import random
import socket
import unittest
from unittest.mock import Mock, patch

from aethron_edge.telemetry.mavlink import PassiveTelemetry, UdpTelemetry
from pymavlink.dialects.v20 import common


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000_000_000
        self.source = PassiveTelemetry(1, 1, clock=lambda: self.now)

    def packet(self, sequence=0, boot=10, system=1, component=1, kind="attitude", **changes):
        encoder = common.MAVLink(None, srcSystem=system, srcComponent=component)
        encoder.seq = sequence
        if kind == "attitude":
            fields = {
                "time_boot_ms": boot,
                "roll": 0.1,
                "pitch": 0.2,
                "yaw": 0.3,
                "rollspeed": 0.4,
                "pitchspeed": 0.5,
                "yawspeed": 0.6,
            }
            fields.update(changes)
            message = common.MAVLink_attitude_message(**fields)
        elif kind == "position":
            message = common.MAVLink_local_position_ned_message(boot, 1, 2, 3, 4, 5, 6)
        else:
            message = common.MAVLink_command_long_message(1, 1, 400, 0, 1, 0, 0, 0, 0, 0, 0)
        return message.pack(encoder)

    def test_real_sdk_packet_units_and_unverified_provenance(self):
        self.source.ingest(self.packet())
        status = self.source.snapshot()
        self.assertEqual(status.state, "OBSERVED_UNVERIFIED")
        sample = status.samples[0]
        self.assertEqual((sample.system_id, sample.component_id), (1, 1))
        self.assertEqual(sample.message, "ATTITUDE")
        self.assertAlmostEqual(sample.values[0], 0.1)
        self.assertEqual(sample.frame, "body_euler")
        self.assertEqual(sample.units, ("rad", "rad", "rad", "rad/s", "rad/s", "rad/s"))
        self.assertEqual(sample.source_boot_ms, 10)
        self.assertEqual(sample.receive_ns, self.now)
        self.assertIsNone(sample.capture_ns)
        self.assertFalse(sample.authenticated)
        self.assertEqual(sample.evidence, "external_unverified")
        self.assertFalse(status.perception_eligible)

    def test_latest_slots_expire_independently_without_new_packets(self):
        self.source.ingest(self.packet())
        self.now += 50_000_000
        self.source.ingest(self.packet(sequence=1, kind="position"))
        self.assertEqual(len(self.source.snapshot().samples), 2)
        self.now += 50_000_001
        status = self.source.snapshot()
        self.assertEqual([s.message for s in status.samples], ["LOCAL_POSITION_NED"])
        self.assertEqual(status.samples[0].frame, "local_ned_unregistered")
        self.now += 50_000_000
        self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        self.assertEqual(self.source.snapshot().samples, ())

    def test_malformed_unsupported_and_spoofed_packets_withdraw_cached_observation(self):
        corrupt = bytearray(self.packet(sequence=1))
        corrupt[-1] ^= 1
        for invalid in (
            bytes(corrupt),
            b"secret\n" * 50,
            b"",
            self.packet()[:-1],
            self.packet() + self.packet(),
            self.packet(system=2),
            self.packet(component=2),
            self.packet(kind="command"),
            self.packet(roll=math.nan),
            self.packet(yaw=math.inf),
        ):
            with self.subTest(size=len(invalid)):
                source = PassiveTelemetry(1, 1, clock=lambda: self.now)
                source.ingest(self.packet())
                source.ingest(invalid)
                status = source.snapshot()
                self.assertEqual(status.state, "UNKNOWN")
                self.assertEqual(status.samples, ())
                self.assertNotIn("secret", repr(status))

    def test_sequence_wrap_duplicates_and_reordering(self):
        self.source.ingest(self.packet(sequence=255))
        self.source.ingest(self.packet(sequence=0, boot=11))
        self.assertEqual(self.source.snapshot().state, "OBSERVED_UNVERIFIED")
        for sequence in (0, 255):
            self.source.ingest(self.packet(sequence=sequence, boot=12))
            self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        self.source.ingest(self.packet(sequence=1, boot=12))
        self.assertEqual(self.source.snapshot().state, "OBSERVED_UNVERIFIED")

    def test_remote_boot_reset_or_wrap_requires_new_session(self):
        for earlier, later in ((100, 1), (0xFFFFFFFF, 0)):
            source = PassiveTelemetry(1, 1, clock=lambda: self.now)
            source.ingest(self.packet(boot=earlier))
            source.ingest(self.packet(sequence=1, boot=later))
            self.assertEqual(source.snapshot().reason, "source_clock_reset")
            source.ingest(self.packet(sequence=2, boot=200))
            self.assertEqual(source.snapshot().state, "UNKNOWN")

    def test_local_clock_rollback_latches_and_close_erases(self):
        self.source.ingest(self.packet())
        self.now -= 1
        self.assertEqual(self.source.snapshot().reason, "local_clock_invalid")
        self.now += 100
        self.source.ingest(self.packet(sequence=1))
        self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        self.source.close()
        self.source.ingest(self.packet(sequence=2))
        self.assertEqual(self.source.snapshot().reason, "closed")

    def test_raised_clock_fault_withdraws_and_latches_before_propagating(self):
        for operation in ("snapshot", "ingest"):
            for error_type in (
                RuntimeError,
                OSError,
                KeyboardInterrupt,
                SystemExit,
                asyncio.CancelledError,
            ):
                with self.subTest(operation=operation, error_type=error_type.__name__):
                    clock = Mock(return_value=self.now)
                    source = PassiveTelemetry(1, 1, clock=clock)
                    try:
                        source.ingest(self.packet())
                        source.ingest(self.packet(sequence=1, kind="position"))
                        self.assertEqual(len(source.snapshot().samples), 2)
                        failure = error_type("private-clock-detail")
                        clock.side_effect = failure
                        with self.assertRaises(error_type) as caught:
                            if operation == "snapshot":
                                source.snapshot()
                            else:
                                source.ingest(self.packet(sequence=2, boot=11))
                        self.assertIs(caught.exception, failure)
                        calls_after_fault = clock.call_count
                        clock.side_effect = None
                        status = source.snapshot()
                        self.assertEqual(status.state, "UNKNOWN")
                        self.assertEqual(status.reason, "local_clock_invalid")
                        self.assertEqual(status.samples, ())
                        self.assertFalse(status.perception_eligible)
                        self.assertNotIn("private-clock-detail", repr(status))
                        source.ingest(self.packet(sequence=3, boot=12))
                        self.assertEqual(source.snapshot(), status)
                        self.assertEqual(clock.call_count, calls_after_fault)
                        source.close()
                        self.assertEqual(source.snapshot().reason, "closed")
                    finally:
                        source.close()

    def test_unexpected_decoder_fault_withdraws_and_latches_before_propagating(self):
        for error_type in (
            RuntimeError,
            OSError,
            KeyboardInterrupt,
            SystemExit,
            asyncio.CancelledError,
        ):
            with self.subTest(error_type=error_type.__name__):
                source = PassiveTelemetry(1, 1, clock=lambda: self.now)
                try:
                    source.ingest(self.packet())
                    source.ingest(self.packet(sequence=1, kind="position"))
                    self.assertEqual(len(source.snapshot().samples), 2)
                    failure = error_type("private-decoder-detail")
                    with patch.object(source._decoder, "decode", side_effect=failure):
                        with self.assertRaises(error_type) as caught:
                            source.ingest(self.packet(sequence=2, boot=11))
                    self.assertIs(caught.exception, failure)
                    status = source.snapshot()
                    self.assertEqual(status.state, "UNKNOWN")
                    self.assertEqual(status.reason, "decoder_fault")
                    self.assertEqual(status.samples, ())
                    self.assertFalse(status.perception_eligible)
                    self.assertNotIn("private-decoder-detail", repr(status))
                    source.ingest(self.packet(sequence=3, boot=12))
                    self.assertEqual(source.snapshot(), status)
                finally:
                    source.close()

    def test_expected_decoder_rejection_remains_recoverable(self):
        self.source.ingest(self.packet())
        with patch.object(
            self.source._decoder, "decode", side_effect=common.MAVError("bad packet")
        ):
            self.source.ingest(self.packet(sequence=1, boot=11))
        self.assertEqual(self.source.snapshot().reason, "invalid_packet")
        self.assertEqual(self.source.snapshot().samples, ())
        self.source.ingest(self.packet(sequence=2, boot=12))
        self.assertEqual(self.source.snapshot().state, "OBSERVED_UNVERIFIED")

    def test_signed_packet_cannot_be_reported_as_authenticated_without_keys(self):
        encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
        encoder.signing.secret_key = bytes(32)
        encoder.signing.sign_outgoing = True
        encoder.signing.link_id = 1
        encoder.signing.timestamp = 100
        packet = common.MAVLink_attitude_message(10, 0, 0, 0, 0, 0, 0).pack(encoder)
        self.source.ingest(packet)
        self.assertEqual(self.source.snapshot().reason, "unsupported_packet")

    def test_sdk_checksum_bypass_configuration_is_refused(self):
        with patch.object(common, "MAVLINK_IGNORE_CRC", "1"):
            with self.assertRaisesRegex(ValueError, "unsafe_mavlink_sdk"):
                PassiveTelemetry(1, 1)

    def test_crc_valid_payload_extension_or_empty_payload_is_rejected(self):
        for payload in (b"", bytes(29)):
            packet = bytearray([0xFD, len(payload), 0, 0, 1, 1, 1, 30, 0, 0]) + payload
            checksum = common.x25crc(packet[1:] + bytes([39])).crc
            packet.extend(checksum.to_bytes(2, "little"))
            self.source.ingest(bytes(packet))
            self.assertEqual(self.source.snapshot().state, "UNKNOWN")

    def test_invalid_configuration_and_bounded_random_wire(self):
        for system, component in ((True, 1), (0, 1), (256, 1), (1, -1), (1, 1.0)):
            with self.assertRaises(ValueError):
                PassiveTelemetry(system, component)
        # Reproducible parser mutations only; never keys, tokens or security entropy.
        rng = random.Random(16031)  # nosec B311
        for _ in range(2000):
            self.source.ingest(rng.randbytes(rng.randrange(400)))
            self.assertEqual(self.source.snapshot().state, "UNKNOWN")
        for _ in range(2000):
            packet = bytearray(self.packet())
            # Exercise the SDK decoder, not only the outer framing guard.
            index = rng.randrange(10, len(packet) - 2)
            packet[index] ^= rng.randrange(1, 256)
            self.source.ingest(bytes(packet))
            self.assertEqual(self.source.snapshot().state, "UNKNOWN")

    def test_loopback_receive_timeout_and_no_transmission(self):
        with (
            UdpTelemetry(self.source, port=0) as receiver,
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender,
        ):
            sender.bind(("127.0.0.1", 0))
            sender.settimeout(0.02)
            sender.sendto(self.packet(), ("127.0.0.1", receiver.port))
            self.assertEqual(receiver.poll().state, "OBSERVED_UNVERIFIED")
            with self.assertRaises(socket.timeout):
                sender.recvfrom(1)
            self.now += 100_000_001
            self.assertEqual(receiver.poll().state, "UNKNOWN")
            sender.sendto(b"x" * 1000, ("127.0.0.1", receiver.port))
            self.assertEqual(receiver.poll().reason, "invalid_packet")
        self.assertEqual(self.source.snapshot().reason, "closed")


if __name__ == "__main__":
    unittest.main()
