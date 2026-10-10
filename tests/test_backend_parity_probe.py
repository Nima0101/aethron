"""Negative controls for synthetic build evidence, without loading backends."""

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import backend_parity_probe as probe


class BackendParityProbe(unittest.TestCase):
    def contents(self):
        return {
            **probe.PAYLOAD,
            "probe_package-0.0.1.dist-info/METADATA": (
                b"Metadata-Version: 2.4\nName: probe-package\nVersion: 0.0.1\n"
                b"Requires-Python: >=3.9\nLicense-Expression: GPL-3.0-only\n\n"
            ),
            "probe_package-0.0.1.dist-info/licenses/LICENSE": b"synthetic license\n",
            "probe_package-0.0.1.dist-info/entry_points.txt": (
                b"[console_scripts]\nprobe-package = probe_pkg:main\n"
            ),
        }

    def validate(self, contents):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "fixture.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for name, value in contents.items():
                    archive.writestr(name, value)
            return probe.validate_wheel(wheel, b"synthetic license\n")

    def test_directory_entries_do_not_change_payload(self):
        self.validate(self.contents())
        self.validate({**self.contents(), "probe_pkg/": b""})

    def test_missing_extra_and_changed_payload_fail(self):
        for defect in ("missing", "extra", "extra_metadata", "changed"):
            with self.subTest(defect=defect):
                contents = self.contents()
                if defect == "missing":
                    del contents["probe_pkg/schema.json"]
                elif defect == "extra":
                    contents["unrelated-private-note.txt"] = b"excluded fixture"
                elif defect == "extra_metadata":
                    contents["unrelated.dist-info/private.txt"] = b"excluded fixture"
                else:
                    contents["probe_pkg/schema.json"] = b"{}"
                with self.assertRaises(AssertionError):
                    self.validate(contents)

    def test_metadata_license_and_entrypoint_changes_fail(self):
        for suffix, replacement in (
            ("/METADATA", b"Name: different\n"),
            ("/licenses/LICENSE", b"different license"),
            ("/entry_points.txt", b"[console_scripts]\nprobe-package=probe_pkg:wrong\n"),
        ):
            with self.subTest(suffix=suffix):
                contents = self.contents()
                name = next(name for name in contents if name.endswith(suffix))
                contents[name] = replacement
                with self.assertRaises(AssertionError):
                    self.validate(contents)

    def test_optimized_interpreter_rejects_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            result = subprocess.run(
                [sys.executable, "-O", probe.__file__, "--tools", directory, "--out", str(output)],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("probe_requires_assertions", result.stderr)
            self.assertFalse(output.exists())
