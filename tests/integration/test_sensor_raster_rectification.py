"""Recorded mono8 remapping: independent rays, invalid masks and strict bounds."""

import importlib
import unittest

from aethron_edge.sensors.geometry import Pinhole
from aethron_edge.sensors.packets import Raster, decode_image
from aethron_edge.sensors.rectification import FisheyeCalibration, LensCalibration


def camera(width, height=1, fx=1.0, fy=1.0, cx=0.0, cy=0.0):
    return Pinhole(width=width, height=height, fx=fx, fy=fy, cx=cx, cy=cy)


def raster(width, data, height=1, step=None, **changes):
    layout = {
        "modality": "lwir",
        "encoding": "mono8",
        "width": width,
        "height": height,
        "step": step or width,
        "is_bigendian": False,
    }
    layout.update(changes)
    return decode_image(layout, data)


def brown(source, output=None, coefficients=(0.0, 0.0, 0.0, 0.0, 0.0), radius=3.0):
    return LensCalibration(
        camera=source, output_camera=output or source, distortion=coefficients, valid_radius=radius
    )


class SensorRasterRectification(unittest.TestCase):
    def rectify(self, frame, lens):
        name = "aethron_edge.sensors.raster_rectification"
        self.assertIsNotNone(importlib.util.find_spec(name), "recorded raster rectifier missing")
        return importlib.import_module(name).rectify_mono8_recorded(frame, lens)

    def test_identity_preserves_zero_counts_and_ignores_padding(self):
        frame = raster(3, bytes([0, 1, 255, 99, 40, 50, 60, 88]), height=2, step=4)
        result = self.rectify(frame, brown(camera(3, 2)))
        self.assertEqual(result.data, bytes([0, 1, 255, 40, 50, 60]))
        self.assertEqual(result.validity, b"\x01" * 6)
        self.assertEqual((result.width, result.height, result.modality), (3, 2, "lwir"))
        self.assertEqual(result.sample(0, 0), 0)
        self.assertFalse(result.live_evidence)
        self.assertEqual(result.version, 1)
        self.assertNotIn("data=", repr(result))
        self.assertEqual(frame.data[-1], 88)

    def test_forward_radial_ray_and_outside_image_mask(self):
        # Output x=1 -> distorted x=1.5 -> source u=3. Output x=2 -> u=12 (outside).
        result = self.rectify(
            raster(7, bytes(range(7))),
            brown(camera(7, fx=2.0), camera(3), (0.5, 0.0, 0.0, 0.0, 0.0)),
        )
        self.assertEqual(result.data, b"\x00\x03\x00")
        self.assertEqual(result.validity, b"\x01\x01\x00")
        self.assertIsNone(result.sample(2, 0))

    def test_tangential_terms_and_nearest_tie_rule(self):
        # x=1,y=0,p1=.01,p2=.02 -> xd=1.06,yd=.01 -> u=21.2,v=.2.
        source = raster(25, bytes(range(25)) * 2, height=2)
        result = self.rectify(
            source,
            brown(
                camera(25, 2, fx=20.0, fy=20.0), camera(2), (0.0, 0.0, 0.01, 0.02, 0.0), radius=1.0
            ),
        )
        self.assertEqual(result.sample(1, 0), 21)
        tied = self.rectify(raster(3, b"\x0a\x14\x1e"), brown(camera(3), camera(2, fx=2.0)))
        self.assertEqual(tied.data, b"\x0a\x14")  # .5 chooses the larger source index.

    def test_fisheye_zero_coefficients_are_equidistant_not_identity(self):
        source = raster(30, bytes(range(30)), modality="nir")
        for k1, expected in ((0.0, 16), (0.1, 17)):
            lens = FisheyeCalibration(
                model="opencv_fisheye_v1",
                camera=camera(30, fx=20.0),
                output_camera=camera(2),
                distortion=(k1, 0.0, 0.0, 0.0),
                valid_theta_rad=1.0,
            )
            result = self.rectify(source, lens)
            self.assertEqual(result.data, bytes([0, expected]))
            self.assertEqual(result.validity, b"\x01\x01")
            self.assertEqual(result.modality, "nir")

    def test_domain_and_unrounded_source_bounds_never_clamp(self):
        result = self.rectify(raster(3, b"\x01\x02\x03"), brown(camera(3), radius=1.0))
        self.assertEqual(result.validity, b"\x01\x01\x00")
        outside = self.rectify(raster(3, b"\x01\x02\x03"), brown(camera(3), camera(2, cx=0.1)))
        self.assertIsNone(outside.sample(0, 0))  # -.1 must not round into the image.
        for coordinates in ((True, 0), (-1, 0), (0, 1), (1.0, 0)):
            with self.assertRaisesRegex(ValueError, "^pixel_outside_frame$"):
                result.sample(*coordinates)

    def test_invalid_layout_forged_models_and_output_budget_reject(self):
        frame = raster(2, b"\x01\x02")
        lens = brown(camera(2))
        cases = [
            (Raster(frame.layout, b""), lens),
            (Raster(frame.layout, bytearray(b"\x01\x02")), lens),
            (raster(2, b"\x00" * 4, step=4, encoding="mono16"), lens),
            (frame, brown(camera(3))),
            (frame, lens.model_copy(update={"valid_radius": -1.0})),
            (frame, lens.model_copy(update={"camera": camera(2, fx=1e-10)})),
            (frame, brown(camera(2), camera(641, 512))),
            (frame, {}),
        ]
        for data, calibration in cases:
            with self.subTest(data=data, calibration=calibration):
                with self.assertRaisesRegex(ValueError, "^invalid_raster_rectification$"):
                    self.rectify(data, calibration)

    def test_fractional_identity_and_exact_output_budget(self):
        source = raster(3, bytes(range(6)), height=2)
        result = self.rectify(source, brown(camera(3, 2, fx=1.3, fy=2.7, cx=0.3, cy=0.2)))
        self.assertEqual(result.data, source.data)
        self.assertEqual(result.validity, b"\x01" * 6)
        result = self.rectify(
            raster(2, b"\x01\x02\x03\x04", height=2),
            brown(camera(2, 2), camera(640, 512, fx=640.0, fy=512.0)),
        )
        self.assertEqual(len(result.data), 640 * 512)
        self.assertEqual(result.validity, b"\x01" * (640 * 512))
        self.assertEqual(result.sample(639, 511), 4)

    def test_fisheye_declared_domain_masks_in_bounds_source(self):
        lens = FisheyeCalibration(
            model="opencv_fisheye_v1",
            camera=camera(30, fx=20.0),
            output_camera=camera(2),
            distortion=(0.0, 0.0, 0.0, 0.0),
            valid_theta_rad=0.5,
        )
        result = self.rectify(raster(30, bytes(range(30))), lens)
        self.assertEqual(result.validity, b"\x01\x00")
        self.assertIsNone(result.sample(1, 0))
