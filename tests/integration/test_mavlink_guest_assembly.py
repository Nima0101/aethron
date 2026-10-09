"""Optional offline SDK staging must reject incomplete/tampered closures."""

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class MavlinkGuestAssembly(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "guest", ROOT / "packaging/appliance/image/prepare.py"
        )
        self.prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.prepare)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = self.root / "context"
        self.context.mkdir()
        (self.context / "dependencies").mkdir()
        (self.context / "requirements.lock").write_text("# existing ROS closure\n")
        self.wheels = self.root / "wheels"
        self.wheels.mkdir()
        self.expected = {}
        entries = []
        for name in ("pymavlink", "fastcrc", "lxml"):
            filename = f"{name}-1.0-py3-none-any.whl"
            content = name.encode()
            digest = hashlib.sha256(content).hexdigest()
            (self.wheels / filename).write_bytes(content)
            self.expected[filename] = digest
            entries.append(f"{name}==1.0 --hash=sha256:{digest}")
        self.lock = self.root / "mavlink.lock"
        self.lock.write_text("\n".join(entries) + "\n")

    def stage(self):
        with patch.object(self.prepare, "MAVLINK_LOCK", self.lock):
            return self.prepare.stage_mavlink_inputs(self.context, self.wheels)

    def test_valid_closure_extends_existing_requirements_without_credentials(self):
        result = self.stage()
        self.assertEqual(result, self.expected)
        self.assertEqual(
            {p.name for p in (self.context / "dependencies").iterdir()}, set(self.expected)
        )
        self.assertTrue(
            (self.context / "requirements.lock").read_text().startswith("# existing ROS closure\n")
        )
        self.assertIn("pymavlink==1.0", (self.context / "requirements.lock").read_text())
        self.assertEqual(
            {p.name for p in self.context.iterdir()}, {"requirements.lock", "dependencies"}
        )

    def test_missing_tampered_extra_and_symlink_wheels_are_refused_before_copy(self):
        first = self.wheels / next(iter(self.expected))
        for mode in ("missing", "tampered", "extra", "symlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as scratch:
                original = first.read_bytes()
                extra = self.wheels / "unexpected.whl"
                if mode == "missing":
                    first.unlink()
                elif mode == "tampered":
                    first.write_bytes(b"wrong")
                elif mode == "extra":
                    extra.write_bytes(b"unknown")
                else:
                    target = Path(scratch) / "target"
                    target.write_bytes(original)
                    first.unlink()
                    first.symlink_to(target)
                try:
                    with self.assertRaisesRegex(ValueError, "invalid_mavlink_dependencies"):
                        self.stage()
                    self.assertEqual(list((self.context / "dependencies").iterdir()), [])
                finally:
                    first.unlink(missing_ok=True)
                    first.write_bytes(original)
                    extra.unlink(missing_ok=True)

    def test_wrong_python_guest_is_refused_before_build(self):
        with self.assertRaisesRegex(ValueError, "mavlink_requires_python312_ros_guest"):
            self.prepare.prepare(
                self.root, self.wheels, self.root / "absent-key", mavlink_dependencies=self.wheels
            )


if __name__ == "__main__":
    unittest.main()
