"""Reject impossible source parity before decompressing wheel members."""

import io
import unittest
import zipfile
from unittest.mock import patch

from scripts import package_check


def source_wheel(package, layout, contents):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        wheel.writestr(layout + package + "/module.py", contents)
    return buffer.getvalue()


class WheelSourceSize(unittest.TestCase):
    def test_size_mismatch_rejects_without_opening_compressed_members(self):
        expected = b"VALUE = 1\n"
        for package in ("aethron", "aethron_edge"):
            payload = {package + "/module.py": expected}
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for contents in (b"", expected[:-1], expected + b"\n", b"#" * (4 * 1024 * 1024)):
                    raw = source_wheel(package, layout, contents)
                    with self.subTest(package=package, layout=layout, size=len(contents)):
                        # The large fixture compresses to a small archive. No
                        # wall-time/RSS threshold or giant allocation is needed
                        # to demonstrate that rejection precedes decompression.
                        self.assertLess(len(raw), 8192)
                        with patch.object(
                            zipfile.ZipFile, "open", autospec=True, side_effect=zipfile.ZipFile.open
                        ) as opened:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(raw, payload, package)
                            opened.assert_not_called()

    def test_equal_size_still_requires_equal_bytes(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for expected in (b"", b"VALUE = 1\n"):
                    payload = {package + "/module.py": expected}
                    with self.subTest(package=package, layout=layout, size=len(expected)):
                        package_check.validate_source_payload(
                            source_wheel(package, layout, expected), payload, package
                        )
                        if expected:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(
                                    source_wheel(package, layout, b"VALUE = 2\n"), payload, package
                                )
