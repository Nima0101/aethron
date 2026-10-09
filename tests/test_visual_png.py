"""Canonical visual PNGs preserve pixels without a platform compressor."""

import io
import unittest
from unittest.mock import patch

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "Pillow required for visual rendering")
class CanonicalPNG(unittest.TestCase):
    def test_pixels_round_trip_across_stored_block_boundaries(self):
        from scripts.temporal_visuals import png_bytes

        # RGB scanline sizes immediately below, at, and above 65535 bytes.
        for width, height in ((1, 1), (21844, 1), (1456, 15), (21845, 1), (21845, 2)):
            with self.subTest(size=(width, height)):
                pixels = bytes(i % 251 for i in range(width * height * 3))
                original = Image.frombytes("RGB", (width, height), pixels)
                with patch("zlib.compress", side_effect=AssertionError("platform compressor")):
                    encoded = png_bytes(original)
                    self.assertEqual(encoded, png_bytes(original))
                with Image.open(io.BytesIO(encoded)) as decoded:
                    decoded.load()
                    self.assertEqual(decoded.mode, "RGB")
                    self.assertEqual(decoded.size, original.size)
                    self.assertEqual(decoded.tobytes(), pixels)

    def test_fixed_one_pixel_representation_and_unsupported_mode(self):
        from scripts.temporal_visuals import png_bytes

        # PNG signature, RGB IHDR, one stored DEFLATE block and IEND.
        expected = bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
            "0000000f494441547801010400fbff00ff0000030101008d1de582"
            "0000000049454e44ae426082"
        )
        self.assertEqual(png_bytes(Image.new("RGB", (1, 1), "red")), expected)
        with self.assertRaises(ValueError):
            png_bytes(Image.new("RGBA", (1, 1)))
