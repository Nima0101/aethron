"""Contract for the optional native output-admission slice; no model execution."""

import importlib.util
import random
import unittest

import numpy as np

if importlib.util.find_spec("aethron_vision_native"):
    from aethron_vision_native import validate_output
else:
    validate_output = None


class OutputBounds(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(validate_output, "build/install the native output validator")
        self.raw = np.zeros((1, 8400, 85), dtype=np.float32)

    def test_valid_extremes_readonly_and_unaligned(self):
        self.raw[:, :, :4] = np.finfo(np.float32).max
        self.raw[:, :, 4:] = 1
        self.assertTrue(validate_output(self.raw))
        self.raw[:, :, :4] *= -1
        self.raw[:, :, 4:] = -0.0
        self.raw.setflags(write=False)
        self.assertTrue(validate_output(self.raw))
        unaligned = np.ndarray(
            self.raw.shape, dtype=np.float32, buffer=bytearray(self.raw.nbytes + 1), offset=1
        )
        self.assertTrue(validate_output(unaligned))

    def test_nonfinite_and_probability_bounds(self):
        for row in (0, 8399):
            for column in (0, 3, 4, 84):
                for value in (np.nan, np.inf, -np.inf):
                    self.raw[0, row, column] = value
                    self.assertFalse(validate_output(self.raw))
                    self.raw[0, row, column] = 0
        for value in (
            np.nextafter(np.float32(0), np.float32(-1)),
            np.nextafter(np.float32(1), np.float32(2)),
        ):
            self.raw[0, 8399, 84] = value
            self.assertFalse(validate_output(self.raw))

    def test_buffer_contract_rejects_layout_type_shape(self):
        for raw in (
            None,
            b"",
            self.raw.astype(np.float64),
            self.raw.astype(">f4"),
            self.raw.reshape(8400, 85),
            self.raw[:, :-1],
            self.raw[:, ::-1],
            np.asfortranarray(self.raw),
            self.raw.astype(object),
        ):
            with (
                self.subTest(kind=type(raw)),
                self.assertRaisesRegex(ValueError, "^invalid_input$"),
            ):
                validate_output(raw)

    def test_repeated_validation_never_changes_input(self):
        self.raw[:, :, 4:] = 0.5
        expected = self.raw.tobytes()
        for _ in range(8):
            self.assertTrue(validate_output(self.raw))
        self.assertEqual(self.raw.tobytes(), expected)

    def test_seeded_ieee_bits_match_independent_numpy_predicates(self):
        rng = random.Random(20261010)
        bits_view = self.raw.view(np.uint32)
        patterns = [0x7F800001, 0xFF800001, 0x80000000, 0x7F7FFFFF]
        patterns.extend(rng.getrandbits(32) for _ in range(64))
        for bits in patterns:
            for column in (0, 84):
                bits_view[0, 8399, column] = bits
                probabilities = self.raw[:, :, 4:]
                expected = bool(
                    np.isfinite(self.raw).all()
                    and (probabilities >= 0).all()
                    and (probabilities <= 1).all()
                )
                self.assertEqual(validate_output(self.raw), expected)
                bits_view[0, 8399, column] = 0


class RGBPacking(unittest.TestCase):
    def setUp(self):
        import aethron_vision_native

        self.pack = getattr(aethron_vision_native, "pack_rgb", None)
        self.assertIsNotNone(self.pack, "build/install native RGB packing")
        self.source = np.zeros((640, 640, 3), dtype=np.uint8)
        self.output = np.empty((1, 3, 640, 640), dtype=np.float32)

    def test_channels_readonly_source_and_unaligned_output(self):
        self.source[:] = (17, 89, 203)
        self.source.setflags(write=False)
        output = np.ndarray(
            self.output.shape, dtype=np.float32, buffer=bytearray(self.output.nbytes + 1), offset=1
        )
        self.assertIs(self.pack(self.source, output), True)
        for channel, expected in enumerate((17, 89, 203)):
            self.assertTrue((output[0, channel] == expected).all())

    def test_invalid_metadata_or_alias_never_writes(self):
        storage = bytearray(self.output.nbytes)
        aliased_source = np.ndarray(self.source.shape, dtype=np.uint8, buffer=storage)
        aliased_output = np.ndarray(self.output.shape, dtype=np.float32, buffer=storage)
        for source, output in (
            (self.source[:, ::-1], self.output),
            (self.source.astype(np.uint16), self.output),
            (self.source, self.output.astype(np.float64)),
            (self.source, self.output.reshape(3, 640, 640)),
            (aliased_source, aliased_output),
        ):
            before = output.tobytes()
            with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                self.pack(source, output)
            self.assertEqual(output.tobytes(), before)
        self.output.setflags(write=False)
        with self.assertRaisesRegex(ValueError, "^invalid_input$"):
            self.pack(self.source, self.output)

    def test_pattern_parity_and_buffer_release(self):
        self.source[:] = np.arange(640, dtype=np.uint16)[None, :, None].astype(np.uint8)
        expected = np.ascontiguousarray(self.source.transpose(2, 0, 1)[None], dtype=np.float32)
        self.pack(self.source, self.output)
        np.testing.assert_array_equal(self.output, expected)
        self.output.resize((3 * 640 * 640,), refcheck=True)
