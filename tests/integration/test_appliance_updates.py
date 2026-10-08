"""Offline signed updates must survive tamper, interruption and rollback attempts."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from aethron_edge.runtime.updates import UpdateStore


class Updates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = self.root / "test-only.pem"
        self.public = self.root / "test-only.pub"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(self.private)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(self.private), "-pubout", "-out", str(self.public)],
            check=True,
            capture_output=True,
        )
        self.store = UpdateStore(self.root / "installed", self.public)

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self, version, **changes):
        path = self.root / ("bundle-" + str(version))
        path.mkdir()
        data = b"verified offline content"
        (path / "model.bin").write_bytes(data)
        manifest = {
            "schema_version": 1,
            "version": version,
            "config_version": 1,
            "files": {"model.bin": hashlib.sha256(data).hexdigest()},
        }
        manifest.update(changes)
        (path / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(self.private),
                "-in",
                str(path / "manifest.json"),
                "-out",
                str(path / "manifest.sig"),
            ],
            check=True,
            capture_output=True,
        )
        return path

    def test_activate_recover_tamper_and_rollback(self):
        one = self.store.stage_update(self.bundle(1))
        self.store.activate(one)
        self.assertEqual(self.store.recover()["version"], 1)
        two = self.store.stage_update(self.bundle(2))
        self.store.activate(two)
        with self.assertRaises(ValueError):
            self.store.activate(one)
        (two.path / "model.bin").write_bytes(b"corrupted")
        self.assertEqual(
            self.store.recover()["state"], "fault"
        )  # revoked older slot cannot recover

    def test_bad_signature_missing_model_incompatible_and_interrupted_stage(self):
        active = self.store.stage_update(self.bundle(1))
        self.store.activate(active)
        broken = self.bundle(2)
        (broken / "manifest.sig").write_bytes(b"bad")
        with self.assertRaises(ValueError):
            self.store.stage_update(broken)
        missing = self.bundle(3)
        (missing / "model.bin").unlink()
        with self.assertRaises(ValueError):
            self.store.stage_update(missing)
        with self.assertRaises(ValueError):
            self.store.stage_update(self.bundle(4, config_version=2))
        (self.root / "installed" / "interrupted.pending").mkdir()
        self.assertEqual(self.store.recover()["version"], 1)

    def test_symlink_escape_and_factory_reset(self):
        path = self.bundle(1)
        (path / "model.bin").unlink()
        (path / "model.bin").symlink_to(self.public)
        with self.assertRaises(ValueError):
            self.store.stage_update(path)
        path = self.bundle(2)
        self.store.activate(self.store.stage_update(path))
        self.store.factory_reset()
        self.assertEqual(self.store.recover()["state"], "unprovisioned")
