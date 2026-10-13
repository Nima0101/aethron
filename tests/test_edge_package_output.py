"""A package check must not mix a new attempt with retained evidence."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_package_check


class PackageEvidenceOutput(unittest.TestCase):
    def test_existing_output_is_rejected_before_building(self):
        for retained in (
            {},
            {"result.json": b'{"installed_consumer":true}\n', "server.log": b"retained failure\n"},
        ):
            with self.subTest(retained=bool(retained)), tempfile.TemporaryDirectory() as area:
                output = Path(area) / "attempt"
                output.mkdir()
                for name, data in retained.items():
                    (output / name).write_bytes(data)
                with patch.object(
                    edge_package_check.subprocess,
                    "run",
                    side_effect=subprocess.CalledProcessError(1, ["synthetic-build"]),
                ) as build:
                    with self.assertRaises(Exception) as caught:
                        edge_package_check.run(Path(area) / "wheelhouse", output)
                    self.assertIsInstance(caught.exception, FileExistsError)
                    build.assert_not_called()
                self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, retained)

    def test_failed_fresh_attempt_has_no_success_report(self):
        with tempfile.TemporaryDirectory() as area:
            output = Path(area) / "nested" / "attempt"
            with patch.object(
                edge_package_check.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, ["synthetic-build"]),
            ) as build:
                with self.assertRaises(subprocess.CalledProcessError):
                    edge_package_check.run(Path(area) / "wheelhouse", output)
                build.assert_called_once()
            self.assertTrue(output.is_dir())
            self.assertEqual(list(output.iterdir()), [])
