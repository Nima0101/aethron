"""Recorded mono8 remapping: independent rays, invalid masks and strict bounds."""

import importlib
import traceback
import unittest
from dataclasses import FrozenInstanceError, asdict
from unittest.mock import patch

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


class RecordedRasterClaims(unittest.TestCase):
    def test_fixed_error_suppresses_display_but_retains_exception_context(self):
        api = importlib.import_module("aethron_edge.sensors.raster_rectification")
        frame, lens = raster(1, b"\x00"), brown(camera(1))
        sentinel = "private-calibration-detail"
        for rectify in (api.rectify_mono8_recorded, api.rectify_mono16_recorded):
            for error_type in (ValueError, TypeError, AttributeError, OverflowError):
                with self.subTest(entry=rectify.__name__, error=error_type.__name__):
                    original = error_type(sentinel)
                    with patch.object(LensCalibration, "model_validate", side_effect=original):
                        with self.assertRaises(ValueError) as raised:
                            rectify(frame, lens)
                    error = raised.exception
                    self.assertEqual(str(error), "invalid_raster_rectification")
                    self.assertNotIn(sentinel, repr(error))
                    self.assertTrue(error.__suppress_context__)
                    self.assertIsNone(error.__cause__)
                    self.assertIs(error.__context__, original)
                    self.assertIn(sentinel, str(error.__context__))
                    self.assertNotIn(sentinel, "".join(traceback.format_exception(error)))

    def test_unhandled_runtime_and_control_exceptions_propagate(self):
        api = importlib.import_module("aethron_edge.sensors.raster_rectification")
        frame, lens = raster(1, b"\x00"), brown(camera(1))
        for rectify in (api.rectify_mono8_recorded, api.rectify_mono16_recorded):
            for error_type in (RuntimeError, MemoryError, KeyboardInterrupt, SystemExit):
                with self.subTest(entry=rectify.__name__, error=error_type.__name__):
                    original = error_type("injected-fault")
                    with patch.object(LensCalibration, "model_validate", side_effect=original):
                        with self.assertRaises(error_type) as raised:
                            rectify(frame, lens)
                    self.assertIs(raised.exception, original)

    def test_direct_records_do_not_validate_or_freeze_caller_buffers(self):
        api = importlib.import_module("aethron_edge.sensors.raster_rectification")
        for record_type in (api.RectifiedMono8, api.RectifiedMono16):
            with self.subTest(record=record_type.__name__):
                data, validity = bytearray(b"a"), bytearray(b"b")
                record = record_type(-1, 0, "unvalidated", data, validity)
                # Direct construction is storage, not the remapping admission path.
                self.assertEqual((record.width, record.height), (-1, 0))
                with self.assertRaises(FrozenInstanceError):
                    record.width = 1
                data[0], validity[0] = 99, 100
                self.assertEqual(bytes(record.data), b"c")
                self.assertEqual(bytes(record.validity), b"d")
                self.assertFalse(record.live_evidence)

    def test_dataclass_conversion_omits_nonlive_and_version_properties(self):
        api = importlib.import_module("aethron_edge.sensors.raster_rectification")
        for record_type in (api.RectifiedMono8, api.RectifiedMono16):
            with self.subTest(record=record_type.__name__):
                record = record_type(1, 1, "lwir", b"\x00\x00", b"\x01")
                self.assertFalse(record.live_evidence)
                self.assertEqual(record.version, 1)
                self.assertEqual(
                    set(asdict(record)), {"width", "height", "modality", "data", "validity"}
                )

    def test_mask_is_sampling_only_and_repr_is_not_redaction(self):
        api = importlib.import_module("aethron_edge.sensors.raster_rectification")
        for encoding, size in (("mono8", 1), ("mono16", 2)):
            with self.subTest(encoding=encoding):
                frame = raster(2, bytes(2 * size), step=2 * size, encoding=encoding)
                result = getattr(api, f"rectify_{encoding}_recorded")(
                    frame, brown(camera(2), radius=0.5)
                )
                # Identical stored zeros have distinct sampling status, not quality scores.
                self.assertEqual(result.data, bytes(2 * size))
                self.assertEqual(result.validity, b"\x01\x00")
                self.assertEqual(result.sample(0, 0), 0)
                self.assertIsNone(result.sample(1, 0))
                self.assertFalse(result.live_evidence)
                self.assertNotIn("data=", repr(result))
                self.assertNotIn("validity=", repr(result))
                # Generic dataclass conversion still exposes both full buffers.
                serialized = asdict(result)
                self.assertEqual(serialized["data"], result.data)
                self.assertEqual(serialized["validity"], result.validity)


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


class SensorMono16Rectification(unittest.TestCase):
    def rectify(self, frame, lens):
        api = importlib.import_module("aethron_edge.sensors.raster_rectification")
        self.assertTrue(
            callable(getattr(api, "rectify_mono16_recorded", None)), "mono16 API missing"
        )
        return api.rectify_mono16_recorded(frame, lens)

    def frame(self, values, *, width=None, big=False, padding=0):
        width = width or len(values)
        rows = [values[i : i + width] for i in range(0, len(values), width)]
        data = b"".join(
            b"".join(value.to_bytes(2, "big" if big else "little") for value in row)
            + b"\xa5" * padding
            for row in rows
        )
        return raster(
            width,
            data,
            height=len(rows),
            step=width * 2 + padding,
            encoding="mono16",
            is_bigendian=big,
        )

    def test_both_source_orders_produce_exact_little_endian_counts(self):
        values = [0, 255, 256, 32768, 65535, 0x1234]
        expected = b"".join(value.to_bytes(2, "little") for value in values)
        for big in (False, True):
            source = self.frame(values, width=3, big=big, padding=3)
            result = self.rectify(source, brown(camera(3, 2)))
            self.assertEqual(result.data, expected)
            self.assertEqual(result.validity, b"\x01" * 6)
            self.assertEqual([result.sample(x, y) for y in range(2) for x in range(3)], values)
            self.assertEqual(
                (result.version, result.encoding, result.is_bigendian), (1, "mono16", False)
            )
            self.assertFalse(result.live_evidence)
            self.assertEqual(source.data[-3:], b"\xa5" * 3)
            self.assertNotIn("data=", repr(result))

    def test_radial_and_fisheye_keep_high_counts_and_invalid_zero_distinct(self):
        source = self.frame([257 * i for i in range(30)], big=True, padding=1)
        lens = brown(camera(30, fx=2.0), camera(3), (0.5, 0.0, 0.0, 0.0, 0.0), radius=1.0)
        result = self.rectify(source, lens)
        self.assertEqual(result.data, b"\x00\x00\x03\x03\x00\x00")
        self.assertEqual(result.validity, b"\x01\x01\x00")
        self.assertEqual(result.sample(0, 0), 0)
        self.assertIsNone(result.sample(2, 0))
        fisheye = FisheyeCalibration(
            model="opencv_fisheye_v1",
            camera=camera(30, fx=20.0),
            output_camera=camera(2),
            distortion=(0.0, 0.0, 0.0, 0.0),
            valid_theta_rad=1.0,
        )
        self.assertEqual(self.rectify(source, fisheye).sample(1, 0), 4112)
        for coordinates in ((True, 0), (-1, 0), (0, 1), (1.0, 0)):
            with self.assertRaisesRegex(ValueError, "^pixel_outside_frame$"):
                result.sample(*coordinates)

    def test_exact_budget_and_rejected_depth_encoding_or_malformed_buffer(self):
        source = self.frame([65535, 1, 256, 32768], width=2)
        result = self.rectify(source, brown(camera(2, 2), camera(640, 512, fx=640.0, fy=512.0)))
        self.assertEqual((len(result.data), len(result.validity)), (655360, 327680))
        self.assertEqual(result.sample(639, 511), 32768)
        for data, lens in (
            (source, brown(camera(2, 2), camera(641, 512))),
            (Raster(source.layout, source.data[:-1]), brown(camera(2, 2))),
            (raster(2, b"\x01\x02"), brown(camera(2))),
            (
                raster(
                    2,
                    b"\x01\x00\x02\x00",
                    step=4,
                    modality="depth",
                    encoding="16UC1",
                    meters_per_unit=0.001,
                ),
                brown(camera(2)),
            ),
        ):
            with self.subTest(data=data, lens=lens):
                with self.assertRaisesRegex(ValueError, "^invalid_raster_rectification$"):
                    self.rectify(data, lens)
