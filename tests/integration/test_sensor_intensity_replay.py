"""Recorded-only calibration binding; synthetic counts confer no live authority."""

import hashlib
import importlib
import io
import json
import struct
import unittest
from dataclasses import asdict, replace
from unittest.mock import patch

from aethron_edge.sensors.packets import Raster
from aethron_edge.sensors.rectification import FisheyeCalibration
from aethron_edge.sensors.replay import Header, RecordedFrame, read_frames
from test_sensor_raster_rectification import brown, camera, raster


class SensorIntensityReplay(unittest.TestCase):
    def api(self):
        name = "aethron_edge.sensors.intensity_replay"
        self.assertIsNotNone(importlib.util.find_spec(name), "intensity replay binding missing")
        return importlib.import_module(name)

    def fixture(self, *, encoding="mono8", modality="lwir", fisheye=False):
        api = self.api()
        payload = raster(
            3,
            b"\x00\x01\xff\xa5" if encoding == "mono8" else b"\x00\x00\x01\x00\xff\xff\xa5",
            step=4 if encoding == "mono8" else 7,
            encoding=encoding,
            modality=modality,
            is_bigendian=True,
        )
        lens = brown(camera(3), camera(4))
        if fisheye:
            lens = FisheyeCalibration(
                model="opencv_fisheye_v1",
                camera=camera(3),
                output_camera=camera(4),
                distortion=(0.0, 0.0, 0.0, 0.0),
                valid_theta_rad=0.8,
            )
        calibration = api.IntensityCalibration(
            version=1,
            source_id="front",
            coordinate_frame="camera_optical",
            layout=payload.layout,
            lens=lens,
        )
        header = Header(
            version=1,
            source_id="front",
            coordinate_frame="camera_optical",
            sequence=19,
            acquisition_ns=123456,
            clock_domain="recorded_monotonic",
            uncertainty_ns=900,
            modality=modality,
            calibration_sha256=calibration.digest,
            payload_sha256=hashlib.sha256(payload.data).hexdigest(),
            layout=payload.layout,
        )
        return api, calibration, RecordedFrame(header, payload)

    def run_frame(self, api, calibration, frame, pin=None):
        return api.rectify_recorded_intensity(
            frame, calibration, expected_calibration_sha256=pin or calibration.digest
        )

    def test_direct_result_construction_does_not_establish_binding(self):
        api = self.api()
        result = api.RecordedIntensity(None, None, None)
        self.assertIsNone(result.source_header)
        self.assertIsNone(result.calibration)
        self.assertIsNone(result.raster)
        # Properties are representation labels, not proof of successful binding.
        self.assertEqual(result.version, 1)
        self.assertEqual(result.source_evidence, "recorded")
        self.assertFalse(result.live_evidence)

    def test_generic_result_conversion_retains_contents_but_omits_evidence_labels(self):
        api = self.api()
        source = {"private_fixture_marker": "raw-metadata"}
        calibration = {"private_fixture_marker": "calibration-declaration"}
        raster_data = {"data": b"private-fixture-bytes"}
        result = api.RecordedIntensity(source, calibration, raster_data)
        self.assertNotIn("private", repr(result))
        converted = asdict(result)
        self.assertEqual(
            converted,
            {"source_header": source, "calibration": calibration, "raster": raster_data},
        )
        self.assertEqual(set(converted), {"source_header", "calibration", "raster"})
        source["private_fixture_marker"] = "changed"
        self.assertEqual(result.source_header["private_fixture_marker"], "changed")
        self.assertEqual(converted["source_header"]["private_fixture_marker"], "raw-metadata")

    def test_binary_replay_preserves_counts_mask_and_original_metadata(self):
        for encoding in ("mono8", "mono16"):
            for modality in ("lwir", "nir"):
                for fisheye in (False, True):
                    with self.subTest(encoding=encoding, modality=modality, fisheye=fisheye):
                        api, calibration, frame = self.fixture(
                            encoding=encoding, modality=modality, fisheye=fisheye
                        )
                        raw = frame.header.model_dump_json().encode()
                        stream = io.BytesIO(struct.pack(">I", len(raw)) + raw + frame.payload.data)
                        result = self.run_frame(api, calibration, next(read_frames(stream)))
                        self.assertEqual(result.source_header, frame.header)
                        self.assertEqual(result.calibration, calibration)
                        self.assertFalse(result.live_evidence)
                        self.assertEqual(result.source_evidence, "recorded")
                        self.assertEqual(result.version, 1)
                        self.assertEqual(result.raster.sample(0, 0), 0)
                        self.assertEqual(
                            result.raster.sample(1, 0), 1 if encoding == "mono8" else 256
                        )
                        self.assertIsNone(result.raster.sample(3, 0))
                        self.assertNotIn("payload", vars(result))
                        self.assertNotIn("data=", repr(result))

    def test_repeated_call_retains_raw_header_without_freshness_or_output_hash(self):
        api, calibration, frame = self.fixture()
        for _ in range(2):
            result = self.run_frame(api, calibration, frame)
            self.assertEqual(result.source_header, frame.header)
            self.assertEqual(result.source_header.sequence, 19)
            self.assertEqual(result.source_header.acquisition_ns, 123456)
            self.assertEqual(result.source_header.uncertainty_ns, 900)
            self.assertEqual(result.source_header.layout.width, 3)
            self.assertEqual(result.raster.width, 4)
            self.assertEqual(
                result.source_header.payload_sha256,
                hashlib.sha256(frame.payload.data).hexdigest(),
            )
            self.assertNotEqual(
                result.source_header.payload_sha256,
                hashlib.sha256(result.raster.data).hexdigest(),
            )
            self.assertEqual(result.source_evidence, "recorded")
            self.assertFalse(result.live_evidence)

    def test_independent_pin_and_header_binding_checked_before_mapping(self):
        api, calibration, frame = self.fixture()
        for pin in (None, "", "a" * 64, calibration.digest.upper(), 123, True):
            with self.subTest(pin=pin), patch.object(api, "rectify_mono8_recorded") as mapper:
                with self.assertRaisesRegex(ValueError, "^invalid_intensity_replay$"):
                    api.rectify_recorded_intensity(
                        frame, calibration, expected_calibration_sha256=pin
                    )
                mapper.assert_not_called()
        for change in (
            {"source_id": "rear"},
            {"coordinate_frame": "other"},
            {"calibration_sha256": None},
            {"calibration_sha256": "a" * 64},
            {"modality": "nir"},
            {"acquisition_ns": -1},
            {"sequence": True},
            {"clock_domain": "host_monotonic"},
            {"uncertainty_ns": -1},
        ):
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(ValueError, "^invalid_intensity_replay$"),
            ):
                self.run_frame(
                    api, calibration, replace(frame, header=frame.header.model_copy(update=change))
                )

    def test_pin_covers_every_calibration_component(self):
        api, calibration, frame = self.fixture()
        variants = [
            calibration.model_copy(update={"source_id": "rear"}),
            calibration.model_copy(update={"coordinate_frame": "other"}),
            calibration.model_copy(
                update={"layout": calibration.layout.model_copy(update={"is_bigendian": False})}
            ),
        ]
        for change in (
            {"camera": camera(3, fx=2.0)},
            {"output_camera": camera(3)},
            {"distortion": (0.1, 0.0, 0.0, 0.0, 0.0)},
            {"valid_radius": 2.0},
        ):
            variants.append(
                calibration.model_copy(update={"lens": calibration.lens.model_copy(update=change)})
            )
        for other in variants:
            with self.subTest(other=other):
                self.assertNotEqual(other.digest, calibration.digest)
                changed = replace(
                    frame,
                    header=frame.header.model_copy(update={"calibration_sha256": other.digest}),
                )
                with self.assertRaisesRegex(ValueError, "^invalid_intensity_replay$"):
                    self.run_frame(api, other, changed, pin=calibration.digest)
        reordered = dict(reversed(list(calibration.model_dump().items())))
        self.assertEqual(
            api.IntensityCalibration.model_validate(reordered).digest, calibration.digest
        )

    def test_raw_layout_bytes_and_hash_are_revalidated(self):
        api, calibration, frame = self.fixture()
        layout = frame.payload.layout.model_copy(update={"is_bigendian": False})
        variants = [
            replace(frame, payload=Raster(layout, frame.payload.data)),
            replace(frame, header=frame.header.model_copy(update={"layout": layout})),
            replace(frame, payload=Raster(frame.payload.layout, frame.payload.data[:-1])),
            replace(frame, payload=Raster(frame.payload.layout, bytearray(frame.payload.data))),
            replace(frame, payload=None),
            replace(frame, header=None),
        ]
        for offset in range(len(frame.payload.data)):
            damaged = bytearray(frame.payload.data)
            damaged[offset] ^= 1
            variants.append(replace(frame, payload=Raster(frame.payload.layout, bytes(damaged))))
        for other in variants:
            with (
                self.subTest(other=other),
                self.assertRaisesRegex(ValueError, "^invalid_intensity_replay$"),
            ):
                self.run_frame(api, calibration, other)

    def test_calibration_is_closed_bounded_and_revalidated(self):
        api, calibration, frame = self.fixture()
        for change in (
            {"version": True},
            {"version": 2},
            {"person_id": "x"},
            {"lens": brown(camera(2))},
            {"lens": brown(camera(3), camera(641, 512))},
            {
                "layout": raster(
                    3,
                    b"\x00" * 6,
                    step=6,
                    modality="depth",
                    encoding="16UC1",
                    meters_per_unit=0.001,
                ).layout
            },
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                api.IntensityCalibration.model_validate({**calibration.model_dump(), **change})
        for bad in (
            None,
            calibration.model_copy(update={"version": True}),
            calibration.model_copy(
                update={"lens": calibration.lens.model_copy(update={"valid_radius": -1.0})}
            ),
        ):
            with (
                self.subTest(bad=bad),
                self.assertRaisesRegex(ValueError, "^invalid_intensity_replay$"),
            ):
                self.run_frame(api, bad, frame, pin=calibration.digest)

    def test_digest_matches_explicit_domain_separated_canonical_document(self):
        _, calibration, _ = self.fixture()
        document = json.dumps(
            calibration.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        expected = hashlib.sha256(b"aethron-recorded-intensity-v1\n" + document).hexdigest()
        self.assertEqual(calibration.digest, expected)
