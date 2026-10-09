"""Boot writes belong to a fresh overlay, never to the signed base or prior logs."""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("boot", ROOT / "scripts/appliance_boot_e2e.py")
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


class OverlayLayout(unittest.TestCase):
    def test_separate_runs_never_overwrite_old_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "image"
            image.mkdir()
            (image / "serial.log").write_text("old failed boot")
            first = boot.new_run_directory(image)
            (first / "serial.log").write_text("first run")
            second = boot.new_run_directory(image)
            self.assertNotEqual(first, second)
            self.assertEqual((image / "serial.log").read_text(), "old failed boot")
            self.assertEqual((first / "serial.log").read_text(), "first run")
            with self.assertRaises(FileExistsError):
                boot.new_run_directory(image, first)
            with self.assertRaises(ValueError):
                boot.new_run_directory(image, image)
            with self.assertRaises(ValueError):
                boot.new_run_directory(image, image.parent)

    def test_image_is_read_only_and_guest_drive_is_overlay(self):
        command = boot.vm_command(Path("/image"), Path("/run"), "sha256:abc")
        self.assertIn("/image:/base:ro", command)
        self.assertIn("/run:/out", command)
        self.assertIn("file=/out/rootfs.qcow2,format=qcow2,if=virtio", command)
        self.assertNotIn("file=/base/rootfs.raw,format=raw,if=virtio", command)
        self.assertIn("/base/kernel", command)
        self.assertIn("/base/initrd", command)
        self.assertEqual(command[command.index("-nic") + 1], "none")

    def test_tampered_image_is_rejected_before_any_overlay_or_process(self):
        with (
            patch.object(boot, "verify_image", side_effect=ValueError("invalid_image_hash")),
            patch.object(boot, "new_run_directory") as directory,
            patch.object(boot.subprocess, "Popen") as start,
        ):
            with self.assertRaisesRegex(ValueError, "invalid_image_hash"):
                boot.run(Path("/tampered"), None, 1)
            directory.assert_not_called()
            start.assert_not_called()


@unittest.skipUnless(os.environ.get("AETHRON_VM_TOOLS"), "explicit local VM tool image required")
class ActualOverlay(unittest.TestCase):
    def test_actual_qcow_writes_leave_backing_bytes_and_second_run_pristine(self):
        tool = os.environ["AETHRON_VM_TOOLS"]
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
            image = Path(tmp) / "base"
            image.mkdir()
            base = image / "rootfs.raw"
            with base.open("wb") as stream:
                stream.truncate(8 * 1024 * 1024)
            digest = boot.file_digest(base)
            first, second = boot.new_run_directory(image), boot.new_run_directory(image)
            for output in (first, second):
                boot.create_overlay(image, output, tool)
                self.assertTrue((output / "rootfs.qcow2").is_file())

            def io(output, instruction):
                return subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        "--read-only",
                        "-v",
                        str(image) + ":/base:ro",
                        "-v",
                        str(output) + ":/out",
                        tool,
                        "qemu-io",
                        "-f",
                        "qcow2",
                        "-c",
                        instruction,
                        "/out/rootfs.qcow2",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                ).stdout

            io(first, "write -P 0x5a 0 4096")
            self.assertNotIn("pattern verification failed", io(first, "read -P 0x5a 0 4096"))
            self.assertNotIn("pattern verification failed", io(second, "read -P 0x00 0 4096"))
            self.assertEqual(boot.file_digest(base), digest)
            before = boot.file_digest(first / "rootfs.qcow2")
            with self.assertRaises(FileExistsError):
                boot.create_overlay(image, first, tool)
            self.assertEqual(boot.file_digest(first / "rootfs.qcow2"), before)
