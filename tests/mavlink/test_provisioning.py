"""Private local credential loading; synthetic keys and boot identities only."""

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BOOT = "aeeeeeee-1111-4111-8111-111111111111"


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("aethron_edge.telemetry.provisioning")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "credential.json"
        self.document = {
            "version": 1,
            "boot_id": BOOT,
            "system_id": 1,
            "component_id": 2,
            "key_hex": bytes(range(32)).hex(),
            "link_id": 7,
            "timestamp_floor": 100,
            "issued_ns": 1000,
            "valid_until_ns": 3000,
        }
        self.write()
        self.boot = patch.object(self.api, "current_boot_id", return_value=BOOT).start()
        self.clock = patch.object(self.api.time, "monotonic_ns", return_value=2000).start()
        self.addCleanup(patch.stopall)

    def write(self):
        self.path.write_text(json.dumps(self.document))
        self.path.chmod(0o600)

    def load(self):
        return self.api.load_trust(self.path, system=1, component=2)

    def rejected(self):
        with self.assertRaisesRegex(ValueError, "^invalid_telemetry_credential$") as raised:
            self.load()
        self.assertNotIn(self.document["key_hex"], str(raised.exception))
        self.assertNotIn(str(self.path), str(raised.exception))

    def test_load_preserves_anchor_key_and_deadline_without_renewal(self):
        before = self.path.read_bytes()
        trust = self.load()
        self.assertEqual(trust.key, bytes(range(32)))
        self.assertEqual((trust.link_id, trust.timestamp_floor), (7, 100))
        self.assertEqual((trust.issued_ns, trust.valid_until_ns), (1000, 3000))
        self.clock.return_value = 2999
        self.assertEqual(self.load(), trust)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertNotIn(repr(trust.key), repr(trust))
        self.assertEqual(list(self.directory.iterdir()), [self.path])

    def test_wrong_boot_sender_future_and_expired_grants_are_rejected(self):
        for field, value in (
            ("boot_id", "beeeeeee-1111-4111-8111-111111111111"),
            ("system_id", 3),
            ("component_id", 3),
            ("issued_ns", 2001),
            ("valid_until_ns", 2000),
        ):
            with self.subTest(field=field):
                original = self.document[field]
                self.document[field] = value
                self.write()
                self.rejected()
                self.document[field] = original

    def test_strict_schema_and_bounded_secret(self):
        for field, value in (
            ("version", True),
            ("version", 2),
            ("system_id", True),
            ("link_id", 1.0),
            ("timestamp_floor", -1),
            ("issued_ns", True),
            ("key_hex", "ab" * 33),
            ("key_hex", "zz" * 32),
            ("boot_id", "not-a-boot-id"),
        ):
            with self.subTest(field=field, value=value):
                original = self.document[field]
                self.document[field] = value
                self.write()
                self.rejected()
                self.document[field] = original
        self.document["unexpected"] = "forbidden"
        self.write()
        self.rejected()

    def test_duplicate_malformed_and_oversized_inputs(self):
        for raw in (
            b"{}",
            b"not JSON",
            b"[]",
            b'{"version":1,"version":1}',
            b"[" * 2048,
            b" " * 2049,
        ):
            with self.subTest(size=len(raw)):
                self.path.write_bytes(raw)
                self.rejected()

    def test_private_mode_owner_and_single_link_required(self):
        for mode in (0o644, 0o640, 0o400, 0o1600):
            self.path.chmod(mode)
            self.rejected()
        self.path.chmod(0o600)
        with patch.object(self.api.os, "getuid", return_value=os.getuid() + 1):
            self.rejected()
        os.link(self.path, self.directory / "extra-link")
        self.rejected()

    def test_private_parent_and_no_leaf_or_parent_symlink(self):
        self.directory.chmod(0o755)
        self.rejected()
        self.directory.chmod(0o700)
        actual = self.directory / "actual"
        self.path.rename(actual)
        self.path.symlink_to(actual)
        self.rejected()
        self.path.unlink()
        actual.rename(self.path)
        link = self.directory / "alias"
        link.symlink_to(self.directory, target_is_directory=True)
        self.path = link / "credential.json"
        self.rejected()

    def test_missing_directory_fifo_and_unsupported_boot_fail_closed(self):
        self.path.unlink()
        self.rejected()
        self.assertFalse(self.path.exists())
        self.path.mkdir()
        self.rejected()
        self.path.rmdir()
        os.mkfifo(self.path, 0o600)
        self.rejected()  # Must not block waiting for a FIFO writer.
        self.path.unlink()
        self.write()
        self.boot.side_effect = OSError("unavailable")
        self.rejected()

    def test_time_is_checked_after_file_read(self):
        read = self.api._read_private

        def slow_read(path):
            raw = read(path)
            self.clock.return_value = 3000
            return raw

        with patch.object(self.api, "_read_private", side_effect=slow_read):
            self.rejected()
        self.clock.return_value = False
        self.rejected()

    def test_descriptor_is_closed_when_directory_is_supplied_as_file(self):
        self.path.unlink()
        self.path.mkdir()
        descriptors = []
        original = os.open

        def opened(*args, **kwargs):
            fd = original(*args, **kwargs)
            descriptors.append(fd)
            return fd

        with patch.object(self.api.os, "open", side_effect=opened):
            self.rejected()
        for fd in descriptors:
            try:
                with self.assertRaises(OSError):
                    os.fstat(fd)
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def test_metadata_mutation_during_read_is_refused(self):
        original = os.fstat
        calls = 0

        def changing(fd):
            nonlocal calls
            calls += 1
            if calls == 3:
                self.path.chmod(0o644)
            return original(fd)

        with patch.object(self.api.os, "fstat", side_effect=changing):
            self.rejected()


if __name__ == "__main__":
    unittest.main()
