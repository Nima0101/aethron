"""Bounded source-selection check, not an archive build or wheel qualification."""

import json
import unittest
from pathlib import Path

from setuptools._distutils.filelist import FileList

ROOT = Path(__file__).resolve().parents[2]


class PassportManifestTests(unittest.TestCase):
    def test_source_distribution_selects_consumer_inputs(self):
        required = {
            "examples/passports/README.md",
            "requirements-passport-sensor-conformance.txt",
            "requirements-passport-conformance.txt",
            "requirements-passports.txt",
            "tests/test_passport_schemas.py",
            "tests/interop_consumers/test_sensor_packets.py",
            "tests/interop_consumers/test_ros_status.py",
        }
        for name in ("edge-unknown", "sensor-packet", "sensor-encoding", "ros-status"):
            path = f"examples/interop/{name}-vectors-v1.json"
            required.add(path)
            required.update(json.loads((ROOT / path).read_bytes())["source_sha256"])
        for path in required:
            self.assertTrue((ROOT / path).is_file(), f"missing checkout input: {path}")
        # Only the finite published consumer inputs are candidates in this probe.
        # Unrelated manifest patterns can legitimately warn that they matched no files.
        selected = FileList()
        selected.set_allfiles(sorted(required))
        for line in (ROOT / "MANIFEST.in").read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                selected.process_template_line(line)
        self.assertEqual(sorted(required - set(selected.files)), [], "consumer inputs omitted")


if __name__ == "__main__":
    unittest.main()
