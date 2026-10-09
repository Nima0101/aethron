"""Installed consumer checks for the signed Jazzy appliance image (not its build env)."""

import importlib.util
import sys
import unittest
from pathlib import Path


class RuntimeImage(unittest.TestCase):
    def test_build_only_pip_is_not_in_the_runtime(self):
        self.assertIsNone(importlib.util.find_spec("pip"))
        self.assertFalse((Path(sys.prefix) / "bin/pip").exists())

    def test_isolated_runtime_and_sdk_imports_remain_available(self):
        self.assertTrue(sys.flags.isolated)
        import aethron_edge
        import fastapi
        import rclpy
        from sensor_msgs.msg import Image

        import aethron

        self.assertTrue(all((aethron, aethron_edge, fastapi, rclpy, Image)))

    def test_initial_and_update_bundles_still_verify_in_full(self):
        from aethron_edge.runtime.updates import verify_bundle

        key = Path("/etc/aethron/trust.pub")
        for name, version in (("aethron", 1), ("aethron-update-candidate", 2)):
            manifest = verify_bundle(Path("/opt") / name, key)
            self.assertEqual(manifest["version"], version)
            self.assertIn("venv/bin/python", manifest["files"])
            self.assertIn("venv/ros.env", manifest["files"])
            self.assertIn("ros-depth.json", manifest["files"])


if __name__ == "__main__":
    unittest.main()
