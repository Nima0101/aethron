"""Byte/mask parity against the frozen recorded Python reference, never live."""

import importlib.util
import math
import random
import unittest

from aethron_edge.sensors.geometry import Pinhole
from aethron_edge.sensors.packets import Raster, decode_image
from aethron_edge.sensors.raster_rectification import (
    rectify_mono8_recorded,
    rectify_mono16_recorded,
)
from aethron_edge.sensors.rectification import LensCalibration


class NativeParity(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron_raster_native"), "native wheel missing"
        )
        from aethron_raster_native import rectify_recorded

        return rectify_recorded

    def test_seeded_masks_counts_endian_padding_and_domains(self):
        native = self.api()
        rng = random.Random(20261009)
        for i in range(150):
            width, height = rng.randrange(1, 40), rng.randrange(1, 30)
            c = Pinhole(
                width=width,
                height=height,
                fx=rng.uniform(10, 50),
                fy=rng.uniform(10, 50),
                cx=width / 2,
                cy=height / 2,
            )
            out = (
                c
                if i % 3 == 0
                else Pinhole(
                    width=width, height=height, fx=c.fx * 0.7, fy=c.fy * 0.9, cx=c.cx, cy=c.cy
                )
            )
            lens = LensCalibration(
                camera=c,
                output_camera=out,
                distortion=(
                    rng.random() * 0.2,
                    rng.random() * 0.01,
                    rng.uniform(-0.001, 0.001),
                    rng.uniform(-0.001, 0.001),
                    rng.random() * 0.001,
                )
                if i % 3
                else (0.0,) * 5,
                valid_radius=0.7,
            )
            bpp = i % 2 + 1
            step = width * bpp + 3
            frame = decode_image(
                {
                    "modality": "lwir",
                    "encoding": "mono8" if bpp == 1 else "mono16",
                    "width": width,
                    "height": height,
                    "step": step,
                    "is_bigendian": bool(i % 4),
                },
                rng.randbytes(step * height),
            )
            expected = (rectify_mono8_recorded if bpp == 1 else rectify_mono16_recorded)(
                frame, lens
            )
            self.assertEqual(native(frame, lens), expected, i)

    def test_exact_budget_and_invalid_contracts(self):
        native = self.api()
        c = Pinhole(width=640, height=512, fx=300.0, fy=300.0, cx=320.0, cy=256.0)
        lens = LensCalibration(camera=c, output_camera=c, distortion=(0.0,) * 5, valid_radius=3.0)
        frame = decode_image(
            {
                "modality": "nir",
                "encoding": "mono16",
                "width": 640,
                "height": 512,
                "step": 1280,
                "is_bigendian": True,
            },
            b"\xff\x01" * (640 * 512),
        )
        self.assertEqual(native(frame, lens), rectify_mono16_recorded(frame, lens))
        for f, calibration in (
            (Raster(frame.layout, frame.data[:-1]), lens),
            (frame, lens.model_copy(update={"valid_radius": -1.0})),
            (frame, None),
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_raster_rectification$"):
                native(f, calibration)

    def test_rounding_boundaries_and_internal_buffer_rejections(self):
        native = self.api()
        from aethron_raster_native import _kernel

        c = Pinhole(width=3, height=1, fx=1.0, fy=1.0, cx=0.0, cy=0.0)
        frame = decode_image(
            {
                "modality": "lwir",
                "encoding": "mono8",
                "width": 3,
                "height": 1,
                "step": 3,
                "is_bigendian": False,
            },
            b"\x00\x12\xff",
        )
        for fx in (2.0, math.nextafter(2.0, 0.0), math.nextafter(2.0, 3.0)):
            out = c.model_copy(update={"fx": fx})
            lens = LensCalibration(
                camera=c, output_camera=out, distortion=(0.0,) * 5, valid_radius=3.0
            )
            self.assertEqual(native(frame, lens), rectify_mono8_recorded(frame, lens))
        parameters = (1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        for dims in (
            (3, 1, 3, 1, 0, 3, 1),
            (3, 1, 2147483647, 1, 0, 3, 1),
            (3, 1, 3, 2, 0, 3, 1),
            (3, 1, 3, 1, 0, 1920, 1080),
        ):
            with self.assertRaises(ValueError):
                _kernel.remap(b"", dims, parameters)
