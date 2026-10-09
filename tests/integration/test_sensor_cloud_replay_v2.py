"""Versioned variable-count cloud replay; no ROS SDK or device is required."""

import hashlib
import io
import json
import struct
import unittest

from aethron_edge.sensors.provisioning import recording_frames
from aethron_edge.sensors.replay import read_frames


def packet(sequence, points, *, width=None, height=1, padding=0, version=2, **changes):
    width = len(points) if width is None else width
    data = b"".join(
        b"".join(struct.pack("<fff", *p) for p in points[y * width : (y + 1) * width])
        + b"\x00" * padding
        for y in range(height)
    )
    header = {
        "version": version,
        "source_id": "radar-front",
        "sequence": sequence,
        "acquisition_ns": sequence * 1_000_000,
        "clock_domain": "recorded_monotonic",
        "uncertainty_ns": 1000,
        "coordinate_frame": "radar_front",
        "modality": "radar",
        "calibration_sha256": "a" * 64,
        "payload_sha256": hashlib.sha256(data).hexdigest(),
        "layout": {
            "width": width,
            "height": height,
            "point_step": 12,
            "row_step": width * 12 + padding,
            "is_bigendian": False,
            "fields": [
                {"name": name, "offset": i * 4, "datatype": 7, "count": 1}
                for i, name in enumerate(("x", "y", "z"))
            ],
        },
    }
    layout_changes = changes.pop("layout_changes", {})
    header["layout"].update(layout_changes)
    header.update(changes)
    raw = json.dumps(header).encode()
    return struct.pack(">I", len(raw)) + raw + data


class CloudReplayV2(unittest.TestCase):
    def test_variable_count_empty_and_organized_clouds_preserve_recorded_samples(self):
        raw = (
            packet(1, [(1, 2, 3)])
            + packet(2, [])
            + packet(3, [(4, 5, 6), (float("nan"), 0, 0)], width=1, height=2, padding=4)
        )
        try:
            frames = list(recording_frames(io.BytesIO(raw)))
        except ValueError as exc:
            self.fail(f"valid variable-count v2 recording rejected: {exc}")
        self.assertEqual([len(f.payload.points) for f in frames], [1, 0, 1])
        self.assertEqual(frames[0].payload.points[0].xyz_m, (1, 2, 3))
        self.assertEqual(frames[2].payload.sample_points[0].xyz_m, (4, 5, 6))
        self.assertIsNone(frames[2].payload.sample_points[1])
        self.assertEqual(frames[2].payload.invalid_points, 1)
        self.assertEqual([f.header.acquisition_ns for f in frames], [1000000, 2000000, 3000000])
        self.assertTrue(all(f.live_evidence is False for f in frames))

    def test_v1_remains_fixed_layout_and_versions_cannot_mix(self):
        for first, second in ((1, 1), (1, 2), (2, 1)):
            with self.subTest(versions=(first, second)), self.assertRaises(ValueError):
                list(
                    read_frames(
                        io.BytesIO(
                            packet(1, [(1, 2, 3)], version=first) + packet(2, [], version=second)
                        )
                    )
                )
        # Identical geometry cannot make a version switch acceptable either.
        for first, second in ((1, 2), (2, 1)):
            with self.subTest(versions=(first, second)), self.assertRaises(ValueError):
                list(
                    read_frames(
                        io.BytesIO(packet(1, [], version=first) + packet(2, [], version=second))
                    )
                )
        self.assertEqual(len(list(read_frames(io.BytesIO(packet(1, [], version=1))))), 1)

    def test_v2_rejects_format_provenance_order_and_size_changes(self):
        # Accept the first v2 frame before exercising each negative boundary.
        first = packet(1, [(1, 2, 3)])
        for changes in (
            {"layout_changes": {"is_bigendian": True}},
            {"layout_changes": {"point_step": 16, "row_step": 16}},
            {
                "layout_changes": {
                    "fields": [
                        {"name": name, "offset": i * 4, "datatype": 7, "count": 1}
                        for i, name in enumerate(("y", "x", "z"))
                    ]
                }
            },
            {"source_id": "other"},
            {"modality": "lidar"},
            {"coordinate_frame": "other"},
            {"calibration_sha256": "b" * 64},
            {"acquisition_ns": 0},
            {"payload_sha256": "0" * 64},
            {"layout_changes": {"width": 4097, "row_step": 49164}},
            {"layout_changes": {"row_step": 8388609}},
        ):
            with self.subTest(changes=changes):
                stream = read_frames(io.BytesIO(first + packet(2, [(4, 5, 6)], **changes)))
                self.assertEqual(next(stream).payload.points[0].xyz_m, (1, 2, 3))
                with self.assertRaises(ValueError):
                    next(stream)

        with self.assertRaises(ValueError):
            list(read_frames(io.BytesIO(first + first)))

    def test_provider_withdraws_geometry_for_empty_cloud_and_recovers_with_scene_break(self):
        from aethron_edge.sensors.packets import layout_digest
        from aethron_edge.sensors.provider import GeometryProvider
        from test_sensor_provider import SensorProvider

        helper = SensorProvider()
        helper.setUp()
        layout = next(read_frames(io.BytesIO(packet(1, [])))).header.layout
        calibration = helper.config(
            modality="radar", source_camera=None, layout_sha256=layout_digest(layout)
        )
        metadata = {
            "source_id": calibration.source_id,
            "coordinate_frame": calibration.rig.source_frame,
            "calibration_sha256": calibration.digest,
        }
        raw = b"".join(
            packet(i, points, **metadata)
            for i, points in enumerate(([(0, 0, 5)], [], [(0, 0, 5), (1, 0, 5)]), 1)
        )
        now = 0
        provider = GeometryProvider(
            calibration,
            mode="recorded",
            clock_id="recording",
            clock=lambda: now,
            valid_for_ns=500_000_000,
        )
        try:
            frames = read_frames(io.BytesIO(raw))
            for index, frame in enumerate(frames):
                now = frame.header.acquisition_ns + frame.header.uncertainty_ns
                result = provider.recorded(frame, [0], mount_id="rig_a")
                self.assertEqual(provider.status()["state"], "UNKNOWN")
                if index == 1:
                    self.assertEqual(result.reason, "provider_unavailable")
                    self.assertFalse(provider.status()["geometry_available"])
                else:
                    self.assertEqual(result.points[0].camera_xyz_m, (0.5, 0.0, 5.0))
                    self.assertEqual(result.source_evidence, "recorded")
                    self.assertFalse(result.live_evidence)
                    self.assertTrue(result.scene_break)
        finally:
            provider.close()

    def test_v2_rejects_images_and_retains_finite_appliance_envelope(self):
        from test_sensor_replay import SensorReplay

        with self.assertRaises(ValueError):
            list(read_frames(io.BytesIO(SensorReplay().packet(version=2))))
        for raw in (
            b"".join(packet(i, []) for i in range(301)),
            packet(1, []) + packet(2, [], acquisition_ns=30_001_000_001),
        ):
            frames = recording_frames(io.BytesIO(raw))
            self.assertFalse(next(frames).live_evidence)
            with self.assertRaisesRegex(ValueError, "recording_limit"):
                list(frames)
