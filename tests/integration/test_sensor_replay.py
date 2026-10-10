"""Synthetic binary replay; recorded clocks never become live support."""

import hashlib
import importlib.util
import io
import json
import struct
import tracemalloc
import unittest


class SensorReplay(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.sensors.replay"))
        from aethron_edge.sensors import replay

        return replay

    def packet(self, **changes):
        data = struct.pack("<HH", 0, 2500)
        header = {
            "version": 1,
            "source_id": "depth-front",
            "sequence": 1,
            "acquisition_ns": 123456,
            "clock_domain": "recorded_monotonic",
            "uncertainty_ns": 1000,
            "coordinate_frame": "camera_optical",
            "modality": "depth",
            "calibration_sha256": None,
            "payload_sha256": hashlib.sha256(data).hexdigest(),
            "layout": {
                "modality": "depth",
                "encoding": "16UC1",
                "width": 2,
                "height": 1,
                "step": 4,
                "is_bigendian": False,
                "meters_per_unit": 0.002,
            },
        }
        header.update(changes)
        raw = json.dumps(header).encode()
        return struct.pack(">I", len(raw)) + raw + data

    def test_complete_read_does_not_duplicate_immutable_payload(self):
        api = self.api()
        payload = b"x" * (1024 * 1024)

        class Complete:
            def read(self, size):
                self.requested = size
                return payload

        source = Complete()
        tracemalloc.start()
        try:
            result = api._read(source, len(payload))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result, payload)
        self.assertEqual(source.requested, len(payload))
        self.assertLess(peak, len(payload), "complete immutable read was duplicated")

    def test_stream_contract_failures_and_empty_payload(self):
        api = self.api()

        class Supplied:
            def __init__(self, blocks):
                self.blocks = iter(blocks)

            def read(self, size):
                return next(self.blocks)

        for blocks in ([None], [bytearray(b"ab")], [b"abc"], [b"a", b"bc"], [b"a", b""]):
            with self.subTest(blocks=blocks), self.assertRaises(ValueError):
                api._read(Supplied(blocks), 2)
        self.assertIsNone(api._read(Supplied([b""]), 2, allow_eof=True))
        with self.assertRaises(ValueError):
            api._read(Supplied([b"a", b""]), 2, allow_eof=True)
        self.assertEqual(api._read(Supplied([]), 0), b"")
        self.assertEqual(api._read(Supplied([b"a", b"b"]), 2), b"ab")

    def test_header_parser_preserves_int64_and_rejects_decoded_duplicate_keys(self):
        api = self.api()
        limit = 2**63 - 1
        records = self.packet(sequence=limit - 1, acquisition_ns=limit - 1)
        records += self.packet(sequence=limit, acquisition_ns=limit)
        frames = list(api.read_frames(io.BytesIO(records)))
        self.assertEqual([f.header.sequence for f in frames], [limit - 1, limit])
        self.assertEqual([f.header.acquisition_ns for f in frames], [limit - 1, limit])
        record = self.packet()
        size = struct.unpack(">I", record[:4])[0]
        header, payload = record[4 : 4 + size], record[4 + size :]
        for bad in (
            b'{"sequence":2,' + header[1:],
            b'{"seq\\u0075ence":2,' + header[1:],
            header.replace(b'"width": 2', b'"width": 1, "width": 2'),
        ):
            with (
                self.subTest(header=bad),
                self.assertRaisesRegex(ValueError, "duplicate_header_key"),
            ):
                list(api.read_frames(io.BytesIO(struct.pack(">I", len(bad)) + bad + payload)))

    def test_replays_pixels_with_recorded_provenance(self):
        frames = list(self.api().read_frames(io.BytesIO(self.packet())))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload.depth_m(1, 0), 5.0)
        self.assertEqual(frames[0].header.acquisition_ns, 123456)
        self.assertFalse(frames[0].live_evidence)
        self.assertEqual(list(self.api().read_frames(io.BytesIO())), [])

    def test_rejects_truncated_tampered_and_oversized_records(self):
        api = self.api()
        data = self.packet()
        for bad in (data[:2], data[:-1], data[:-1] + b"X", struct.pack(">I", 16385)):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                list(api.read_frames(io.BytesIO(bad)))

    def test_rejects_identity_live_clock_and_invalid_metadata(self):
        api = self.api()
        for change in (
            {"person_id": "x"},
            {"clock_domain": "host_monotonic"},
            {"sequence": True},
            {"acquisition_ns": -1},
            {"modality": "lwir"},
            {"calibration_sha256": "x"},
            {"version": True},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                list(api.read_frames(io.BytesIO(self.packet(**change))))

    def test_rejects_source_switch_clock_and_sequence_regression(self):
        api = self.api()
        for change in (
            {"sequence": 1},
            {"sequence": 2, "acquisition_ns": 123455},
            {"sequence": 2, "source_id": "different"},
            {"sequence": 2, "calibration_sha256": "a" * 64},
        ):
            with self.assertRaises(ValueError):
                list(api.read_frames(io.BytesIO(self.packet() + self.packet(**change))))
        frames = list(api.read_frames(io.BytesIO(self.packet() + self.packet(sequence=2))))
        self.assertEqual(len(frames), 2)

    def test_short_stream_reads_and_duplicate_keys(self):
        api = self.api()

        class Short(io.BytesIO):
            def read(self, n=-1):
                if n < 0:
                    raise AssertionError("unbounded_read")
                return super().read(min(n, 3))

        self.assertEqual(len(list(api.read_frames(Short(self.packet())))), 1)
        header = b'{"version":1,"version":1}'
        with self.assertRaises(ValueError):
            list(api.read_frames(io.BytesIO(struct.pack(">I", len(header)) + header)))

    def test_deterministic_corruption_fuzz_and_utf8_only(self):
        import random

        api = self.api()
        rng = random.Random(20261008)
        seed = self.packet()
        accepted = rejected = 0
        for _ in range(2000):
            data = bytearray(seed)
            for _ in range(rng.randrange(1, 5)):
                data[rng.randrange(len(data))] = rng.randrange(256)
            if rng.randrange(4) == 0:
                del data[rng.randrange(len(data)) :]
            try:
                frames = list(api.read_frames(io.BytesIO(data)))
            except ValueError:
                rejected += 1
            else:
                accepted += 1
                self.assertTrue(all(frame.live_evidence is False for frame in frames))
        self.assertEqual(accepted + rejected, 2000)
        self.assertGreater(rejected, 1900)
        size = struct.unpack(">I", seed[:4])[0]
        utf16 = seed[4 : 4 + size].decode().encode("utf-16")
        with self.assertRaises(ValueError):
            list(
                api.read_frames(
                    io.BytesIO(struct.pack(">I", len(utf16)) + utf16 + seed[4 + size :])
                )
            )
