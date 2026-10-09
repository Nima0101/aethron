"""Original-data candidate export, independent verification and failed writes."""

import importlib
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_threshold_experiment as fixtures

from aethron.evaluation import candidates, threshold


@unittest.skipIf(
    getattr(fixtures.ThresholdExperiment, "__unittest_skip__", False), "POSIX required"
)
class ThresholdBundle(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ThresholdExperiment()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.model = self.fixture.fit()
        self.card = b"Original synthetic scalar experiment; no physical accuracy claim."
        self.rights = b"Original software fixture only. GPL-3.0-only."
        self.output = self.fixture.root / "export"

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron.evaluation.threshold_bundle"))
        return importlib.import_module("aethron.evaluation.threshold_bundle")

    def export(self, **changes):
        args = {
            "expected_model_sha256": fixtures.digest(self.model),
            "expected_manifest_sha256": fixtures.digest(self.fixture.manifest),
            "expected_protocol_sha256": fixtures.PROTOCOL_SHA256,
            "card": self.card,
            "expected_card_sha256": fixtures.digest(self.card),
            "rights": self.rights,
            "expected_rights_sha256": fixtures.digest(self.rights),
        }
        args.update(changes)
        return self.api().export(
            self.model, self.fixture.manifest, self.fixture.blobs, self.output, **args
        )

    def verify(self, pins):
        return candidates.verify_artifacts(
            (self.output / "candidate.json").read_bytes(),
            (self.output / "manifest.json").read_bytes(),
            self.output / "blobs",
            expected_candidate_sha256=pins["candidate_sha256"],
            expected_manifest_sha256=pins["manifest_sha256"],
            expected_protocol_sha256=pins["protocol_sha256"],
        )

    def test_portable_export_verifies_without_original_directory(self):
        pins = self.export()
        self.assertEqual(json.loads((self.output / "pins.json").read_bytes()), pins)
        self.assertEqual(pins["model_sha256"], fixtures.digest(self.model))
        self.assertEqual(pins["search_sha256"], fixtures.digest(threshold.SEARCH_BYTES))
        for payload in (
            self.model,
            self.card,
            self.rights,
            threshold.PREPROCESSING_BYTES,
            threshold.SEARCH_BYTES,
        ):
            self.assertEqual(
                (self.output / "blobs" / fixtures.digest(payload)).read_bytes(), payload
            )
        self.fixture.blobs.rename(self.fixture.root / "unavailable-source")
        report = self.verify(pins)
        self.assertTrue(report["artifacts_verified"])
        for flag in (
            "rights_verified",
            "signatures_verified",
            "training_verified",
            "preprocessing_verified",
            "qualified",
        ):
            self.assertIs(report[flag], False)
        self.assertFalse(pins["qualified"])
        self.assertNotIn(str(self.fixture.root), json.dumps(pins))
        self.assertEqual((self.output / "manifest.json").read_bytes(), self.fixture.manifest)
        self.assertFalse((self.output / ".pins.pending").exists())

    def test_existing_destinations_and_symlink_aliases_are_never_modified(self):
        outside = self.fixture.root / "outside"
        outside.mkdir()
        marker = outside / "keep"
        marker.write_bytes(b"unchanged")
        for kind in ("directory", "symlink", "file"):
            if kind == "directory":
                self.output.mkdir()
            elif kind == "symlink":
                self.output.symlink_to(outside, target_is_directory=True)
            else:
                self.output.write_bytes(b"existing")
            for suffix in ("", "/", "/."):
                original = self.output
                self.output = str(original) + suffix
                with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                    self.export()
                self.output = original
            if kind == "directory":
                self.assertEqual(list(self.output.iterdir()), [])
                self.output.rmdir()
            else:
                self.output.unlink()
            self.assertEqual(marker.read_bytes(), b"unchanged")
        pins = self.export()
        with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
            self.export()
        self.assertTrue(self.verify(pins)["artifacts_verified"])

    def test_bad_pins_and_metadata_reject_before_creating_output(self):
        for key in (
            "expected_model_sha256",
            "expected_manifest_sha256",
            "expected_protocol_sha256",
            "expected_card_sha256",
            "expected_rights_sha256",
        ):
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"),
            ):
                self.export(**{key: "0" * 64})
            self.assertFalse(self.output.exists())
        for data in (b"", b"x" * (2 * 1024 * 1024 + 1), "private", bytearray(b"x")):
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                self.export(card=data)
            self.assertFalse(self.output.exists())

    def test_failed_copy_never_publishes_completion_pins(self):
        api = self.api()
        for kind in ("tamper", "symlink", "fifo", "oversized"):
            path = self.fixture.blobs / self.fixture.doc["samples"][0]["artifact_sha256"]
            saved = path.read_bytes()
            path.unlink()
            if kind == "tamper":
                path.write_bytes(b"private tampered bytes")
            elif kind == "symlink":
                path.symlink_to(self.fixture.root / "missing")
            elif kind == "fifo":
                os.mkfifo(path)
            else:
                with path.open("wb") as stream:
                    stream.truncate(64 * 1024 * 1024 + 1)
            self.output = self.fixture.root / kind
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                self.export()
            self.assertFalse((self.output / "pins.json").exists())
            path.unlink()
            path.write_bytes(saved)
        self.output = self.fixture.root / "budget"
        with patch.object(api, "MAX_TOTAL_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                self.export()
        self.assertFalse((self.output / "pins.json").exists())
        self.output = self.fixture.root / "write-failure"
        with patch.object(api, "_write", side_effect=OSError("private disk error")):
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                self.export()
        self.assertFalse((self.output / "pins.json").exists())

    def test_export_is_reproducible_and_deduplicates_roles(self):
        first = self.export(card=self.rights, expected_card_sha256=fixtures.digest(self.rights))
        files = {
            str(p.relative_to(self.output)): p.read_bytes()
            for p in self.output.rglob("*")
            if p.is_file()
        }
        self.output = self.fixture.root / "second"
        second = self.export(card=self.rights, expected_card_sha256=fixtures.digest(self.rights))
        self.assertEqual(first, second)
        self.assertEqual(
            files,
            {
                str(p.relative_to(self.output)): p.read_bytes()
                for p in self.output.rglob("*")
                if p.is_file()
            },
        )
        self.assertTrue(self.verify(second)["artifacts_verified"])

    def test_metadata_readback_failure_prevents_completion(self):
        api = self.api()
        write = api._write
        for target in ("candidate.json", "manifest.json"):
            self.output = self.fixture.root / (target + "-corrupt")

            def corrupt(directory_fd, name, data, target=target):
                write(directory_fd, name, data + b" " if name == target else data)

            with patch.object(api, "_write", corrupt):
                with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                    self.export()
            self.assertFalse((self.output / "pins.json").exists())

    def test_cli_exports_then_rejects_bad_card_without_partial_stdout(self):
        self.api()
        f = self.fixture
        inputs = {
            "model": self.model,
            "manifest": f.manifest,
            "card": self.card,
            "rights": self.rights,
        }
        for name, data in inputs.items():
            (f.root / name).write_bytes(data)
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.threshold_bundle",
            str(f.root / "model"),
            "--manifest",
            str(f.root / "manifest"),
            "--blob-dir",
            str(f.blobs),
            "--output-dir",
            str(self.output),
            "--protocol-sha256",
            fixtures.PROTOCOL_SHA256,
            "--card",
            str(f.root / "card"),
            "--rights",
            str(f.root / "rights"),
        ]
        for name, data in inputs.items():
            command += ["--" + name + "-sha256", fixtures.digest(data)]
        result = subprocess.run(command, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.verify(json.loads(result.stdout))["artifacts_verified"])
        (f.root / "card").write_bytes(b"private tampered card")
        result = subprocess.run(command, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"invalid_threshold_bundle\n")
