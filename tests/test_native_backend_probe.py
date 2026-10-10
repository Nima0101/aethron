"""Negative controls for the synthetic optional-native comparison."""

import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import native_backend_probe as probe


class NativeBackendProbe(unittest.TestCase):
    def test_portable_tag_must_not_claim_native_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "fixture.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    "probe_native-0.0.1.dist-info/WHEEL",
                    "Root-Is-Purelib: true\nTag: cp313-cp313-linux_x86_64\n",
                )
            with self.assertRaises(AssertionError):
                probe.validate_wheel(wheel, {}, False)

    def test_native_mode_requires_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "fixture.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    "probe_native-0.0.1.dist-info/WHEEL",
                    "Root-Is-Purelib: false\nTag: cp313-cp313-linux_x86_64\n",
                )
            with self.assertRaises(AssertionError):
                probe.validate_wheel(wheel, {}, True)

    def test_archive_rejects_traversal_links_and_multiple_roots(self):
        for defect in ("traversal", "link", "multiple_roots"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "fixture.tar.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    paths = (
                        ["first/kernel.py", "second/kernel.py"]
                        if defect == "multiple_roots"
                        else ["../escape" if defect == "traversal" else "link"]
                    )
                    for path in paths:
                        member = tarfile.TarInfo(path)
                        if defect == "link":
                            member.type = tarfile.SYMTYPE
                            member.linkname = "../escape"
                        else:
                            member.size = 1
                        tar.addfile(member, io.BytesIO(b"x"))
                target = root / "out"
                target.mkdir()
                with self.assertRaises(AssertionError):
                    probe.extract_sdist(archive, target)
                self.assertFalse((root / "escape").exists())
