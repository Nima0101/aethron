"""The consumer install request must bind the artifacts actually compared."""

import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_package_check


@unittest.skipUnless(importlib.util.find_spec("packaging.utils"), "wheel build dependency")
class PackageInstallBinding(unittest.TestCase):
    def probe(self, mutate_after_comparison=False, mutate_after_read=False):
        inventory = {
            "aethron-0.2.0-py3-none-any.whl": b"synthetic-core",
            "aethron_edge-0.1.0-py3-none-any.whl": b"synthetic-edge",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempt with # fragment"
            captured = []
            read_bytes = Path.read_bytes

            def read_then_change(path):
                data = read_bytes(path)
                if mutate_after_read and path.parent == output / "a":
                    path.write_bytes(b"changed-after-read")
                return data

            def fake_run(args, **kwargs):
                if "build" in args:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir(exist_ok=True)
                    for name, data in inventory.items():
                        (destination / name).write_bytes(data)
                elif "venv" in args:
                    if mutate_after_comparison:
                        for name in inventory:
                            (output / "a" / name).write_bytes(b"changed-after-comparison")
                elif "install" in args and "-r" not in args:
                    captured.append(args)
                    raise RuntimeError("stop_before_install")
                else:
                    self.assertIn("-r", args)
                return subprocess.CompletedProcess(args, 0)

            with (
                patch.object(edge_package_check.package_check, "validate_source_payload"),
                patch.object(edge_package_check.subprocess, "run", side_effect=fake_run),
                patch.object(Path, "read_bytes", read_then_change),
            ):
                with self.assertRaisesRegex(RuntimeError, "^stop_before_install$"):
                    edge_package_check.run(Path(directory) / "wheelhouse", output)
            self.assertFalse((output / "result.json").exists())
            self.assertEqual(len(captured), 1)
            args = captured[0]
            expected = {
                (output / "a" / name).resolve().as_uri()
                + "#sha256="
                + hashlib.sha256(data).hexdigest()
                for name, data in inventory.items()
            }
            self.assertEqual({arg for arg in args if arg.startswith("file:")}, expected)
            for option in ("--require-hashes", "--no-deps", "--force-reinstall", "--no-index"):
                self.assertIn(option, args)
            self.assertNotIn("--find-links", args)

    def test_install_request_uses_both_compared_artifacts(self):
        self.probe(False)

    def test_install_request_retains_compared_hashes_after_mutation(self):
        self.probe(True)

    def test_hash_describes_the_bytes_used_for_comparison(self):
        self.probe(mutate_after_read=True)
