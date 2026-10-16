"""Portable wheel tags cannot certify unverified native import payloads."""

import unittest
import zipfile
from unittest.mock import patch

from test_wheel_data_destinations import wheel_bytes
from test_wheel_tags import replace_tags

from scripts import package_check


class WheelPortableExtensions(unittest.TestCase):
    def test_portable_extensions_reject_but_native_layouts_and_resources_pass(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for extension in ("module.so", "module.abi3.so", "module.cp313-win_amd64.pyd"):
                    raw, payload = wheel_bytes(
                        package, {layout + f"{package}/{extension}": b"inert native fixture"}
                    )
                    with self.subTest(package=package, layout=layout, extension=extension):
                        # Both metadata and filename agree; source parity alone
                        # misses the additional native import destination.
                        with patch.object(
                            zipfile.ZipFile, "read", autospec=True, side_effect=zipfile.ZipFile.read
                        ) as read:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(
                                    raw,
                                    payload,
                                    package,
                                    wheel_filename=f"{package}-0.2.0-py3-none-any.whl",
                                )
                            read.assert_not_called()
                        # Admission is not native binary qualification. Preserve
                        # the existing platform-specific verification boundary.
                        native = replace_tags(raw, b"Tag: cp313-cp313-linux_x86_64\n")
                        package_check.validate_source_payload(
                            native,
                            payload,
                            package,
                            wheel_filename=f"{package}-0.2.0-cp313-cp313-linux_x86_64.whl",
                        )
            raw, payload = wheel_bytes(
                package,
                {
                    f"{package}/module.so.txt": b"example",
                    f"{package}-0.2.0.dist-info/licenses/example.so": b"example",
                    f"{package}-0.2.0.data/data/share/example.pyd": b"example",
                },
            )
            package_check.validate_source_payload(
                raw, payload, package, wheel_filename=f"{package}-0.2.0-py3-none-any.whl"
            )
