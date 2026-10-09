"""P2 packet tests use synthetic bytes, not physical sensor evidence."""

import importlib.util
import struct
import unittest


class SensorPackets(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron_edge.sensors"), "sensor packet implementation missing"
        )
        from aethron_edge.sensors import packets

        return packets

    def image(self, **changes):
        return dict(
            modality="lwir",
            encoding="mono16",
            width=2,
            height=2,
            step=6,
            is_bigendian=False,
            **changes,
        )

    def test_raw_thermal_counts_preserve_depth_endianness_and_padding(self):
        api = self.api()
        for big in (False, True):
            spec = self.image()
            spec["is_bigendian"] = big
            data = struct.pack((">" if big else "<") + "3H3H", 1, 65530, 999, 400, 700, 888)
            frame = api.decode_image(spec, data)
            self.assertEqual(
                [frame.sample(0, 0), frame.sample(1, 0), frame.sample(0, 1), frame.sample(1, 1)],
                [1, 65530, 400, 700],
            )
            self.assertEqual(frame.units, "counts")
            with self.assertRaises(ValueError):
                frame.depth_m(0, 0)

    def test_depth_scale_invalid_depth_and_nir_are_distinct(self):
        api = self.api()
        spec = {
            "modality": "depth",
            "encoding": "16UC1",
            "width": 2,
            "height": 1,
            "step": 4,
            "is_bigendian": False,
            "meters_per_unit": 0.002,
        }
        frame = api.decode_image(spec, struct.pack("<HH", 0, 2500))
        self.assertIsNone(frame.depth_m(0, 0))
        self.assertEqual(frame.depth_m(1, 0), 5)
        del spec["meters_per_unit"]
        with self.assertRaises(ValueError):
            api.decode_image(spec, b"\0" * 4)
        floating = {
            "modality": "depth",
            "encoding": "32FC1",
            "width": 2,
            "height": 1,
            "step": 8,
            "is_bigendian": True,
            "meters_per_unit": 1.0,
        }
        frame = api.decode_image(floating, struct.pack(">ff", float("nan"), -1))
        self.assertIsNone(frame.depth_m(0, 0))
        self.assertIsNone(frame.depth_m(1, 0))
        nir = {
            "modality": "nir",
            "encoding": "mono8",
            "width": 2,
            "height": 1,
            "step": 2,
            "is_bigendian": False,
        }
        self.assertEqual(api.decode_image(nir, b"\x00\xff").sample(1, 0), 255)

    def test_images_reject_malformed_or_identity_metadata(self):
        api = self.api()
        spec = self.image()
        for change in (
            {"width": True},
            {"height": 1081},
            {"step": 3},
            {"encoding": "rgb8"},
            {"person_id": "persistent"},
            {"meters_per_unit": 1.0},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                api.decode_image(dict(spec, **change), bytes(12))
        for data in (bytes(11), bytes(13), bytearray(12)):
            with self.assertRaises(ValueError):
                api.decode_image(spec, data)

    def cloud(self):
        return {
            "width": 2,
            "height": 1,
            "point_step": 16,
            "row_step": 36,
            "is_bigendian": False,
            "fields": [
                {"name": n, "offset": 4 * i, "datatype": 7, "count": 1}
                for i, n in enumerate(("x", "y", "z", "radial_velocity"))
            ],
        }

    def test_point_cloud_padding_endianness_and_missing_points(self):
        api = self.api()
        spec = self.cloud()
        for big in (False, True):
            spec["is_bigendian"] = big
            data = struct.pack(
                (">" if big else "<") + "8f", 1, 2, 3, -4, float("nan"), 0, 0, 0
            ) + bytes(4)
            cloud = api.decode_cloud(spec, data)
            self.assertEqual(len(cloud.points), 1)
            self.assertEqual(cloud.invalid_points, 1)
            self.assertEqual(cloud.sample_points, (cloud.points[0], None))
            self.assertEqual(cloud.points[0].xyz_m, (1, 2, 3))
            self.assertEqual(cloud.points[0].radial_velocity_mps, -4)

    def test_cloud_rejects_unknown_overlapping_truncated_and_huge_layouts(self):
        api = self.api()
        spec = self.cloud()
        mutations = [
            dict(spec, width=4097),
            dict(spec, row_step=20),
            dict(spec, person_id="x"),
            dict(
                spec,
                fields=spec["fields"]
                + [{"name": "track_id", "offset": 0, "datatype": 7, "count": 1}],
            ),
        ]
        overlap = [dict(f) for f in spec["fields"]]
        overlap[1]["offset"] = 0
        mutations.append(dict(spec, fields=overlap))
        for value in mutations:
            with self.assertRaises(ValueError):
                api.decode_cloud(value, bytes(36))
        with self.assertRaises(ValueError):
            api.decode_cloud(spec, bytes(35))

    def test_rectified_depth_projection_and_euclidean_range(self):
        self.api()
        from aethron_edge.sensors.geometry import Pinhole

        camera = Pinhole(width=4, height=4, fx=2.0, fy=2.0, cx=1.0, cy=1.0)
        xyz = camera.deproject(3.0, 1.0, 2.0)
        self.assertEqual(xyz, (2.0, 0.0, 2.0))
        self.assertEqual(camera.project(xyz), (3.0, 1.0))
        self.assertAlmostEqual(camera.range_m(xyz), 8**0.5)
        for xyz in ((0, 0, 0), (0, 0, -1), (float("nan"), 0, 1)):
            with self.assertRaises(ValueError):
                camera.project(xyz)
        with self.assertRaises(ValueError):
            Pinhole(width=4, height=4, fx=0.0, fy=2.0, cx=1.0, cy=1.0)

    def test_geometry_rejects_malformed_and_overflow_inputs(self):
        from aethron_edge.sensors.geometry import Pinhole

        camera = Pinhole(width=4, height=4, fx=2.0, fy=2.0, cx=1.0, cy=1.0)
        for point in (None, 3, "123", (0, 0, 10**400), (False, 0, 1)):
            for operation in (camera.project, camera.range_m):
                with self.subTest(point_type=type(point).__name__), self.assertRaises(ValueError):
                    operation(point)
        with self.assertRaises(ValueError):
            camera.deproject(10**400, 0, 1)

    def test_float64_organized_cloud_and_empty_frame(self):
        api = self.api()
        spec = {
            "width": 1,
            "height": 2,
            "point_step": 24,
            "row_step": 32,
            "is_bigendian": True,
            "fields": [
                {"name": n, "offset": 8 * i, "datatype": 8, "count": 1}
                for i, n in enumerate(("x", "y", "z"))
            ],
        }
        data = struct.pack(">3d", 1, 2, 3) + bytes(8) + struct.pack(">3d", 4, 5, 6) + bytes(8)
        self.assertEqual(
            [p.xyz_m for p in api.decode_cloud(spec, data).points], [(1, 2, 3), (4, 5, 6)]
        )
        spec.update(width=0, height=1, row_step=0)
        self.assertEqual(api.decode_cloud(spec, b"").points, ())
