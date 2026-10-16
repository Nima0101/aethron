"""Native reduction must preserve first-product ties and reject malformed input."""

import unittest

import aethron_vision_native as native
import numpy as np


class ScoreReduction(unittest.TestCase):
    def select(self, raw):
        self.assertTrue(hasattr(native, "select_scores"), "native score reduction missing")
        categories, confidence = native.select_scores(raw)
        self.assertIs(type(categories), bytes)
        self.assertIs(type(confidence), bytes)
        return np.frombuffer(categories, dtype=np.uint8), np.frombuffer(
            confidence, dtype=np.float32
        )

    def test_first_product_tie_signed_zero_and_underflow(self):
        raw = np.zeros((1, 8400, 85), dtype=np.float32)
        raw[0, 0, 4] = 0.5
        raw[0, 0, 8:10] = 0.75
        raw[0, 1, 4] = np.nextafter(np.float32(0), np.float32(1))
        raw[0, 1, 6] = 0.25  # all products round to zero: first class still wins
        raw[0, 2, 4] = -0.0
        raw[0, 8399, 4] = 1
        raw[0, 8399, 84] = 1
        cat, score = self.select(raw)
        np.testing.assert_array_equal(cat[[0, 1, 2, 8399]], [3, 0, 0, 79])
        np.testing.assert_array_equal(score[[0, 1, 8399]], [0.375, 0, 1])
        self.assertEqual(int(score.view(np.uint32)[2]), 0x80000000)

    def test_seeded_bit_parity_readonly_unaligned_and_owned_outputs(self):
        rng = np.random.default_rng(20261010)
        for offset in (0, 1):
            raw = np.ndarray(
                (1, 8400, 85), dtype=np.float32, buffer=bytearray(2856001), offset=offset
            )
            raw[:] = rng.random(raw.shape, dtype=np.float32)
            raw.flags.writeable = False
            cat, score = self.select(raw)
            products = raw[0, :, 4, None] * raw[0, :, 5:]
            expected = products.argmax(axis=1)
            np.testing.assert_array_equal(cat, expected)
            np.testing.assert_array_equal(
                score.view(np.uint32), products[np.arange(8400), expected].view(np.uint32)
            )
            self.assertFalse(cat.flags.writeable)
            self.assertFalse(score.flags.writeable)
            self.assertFalse(np.shares_memory(score, raw))

    def test_rejects_bad_shape_type_layout_or_values(self):
        raw = np.zeros((1, 8400, 85), dtype=np.float32)
        invalid = [None, raw[:, :-1], raw.astype(np.float64), raw[:, ::-1]]
        for column, value in ((0, np.inf), (4, -0.1), (84, 1.01), (6, np.nan)):
            bad = raw.copy()
            bad[0, 8399, column] = value
            invalid.append(bad)
        self.assertTrue(hasattr(native, "select_scores"), "native score reduction missing")
        for value in invalid:
            with self.subTest(kind=type(value)):
                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                    native.select_scores(value)
