"""Relocated offline bundles require external pins and complete verified bytes."""

import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_threshold_bundle as fixtures

from aethron.evaluation import threshold, threshold_bundle


@unittest.skipIf(getattr(fixtures.ThresholdBundle, "__unittest_skip__", False), "POSIX required")
class ThresholdBundleReader(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ThresholdBundle()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.pins = self.fixture.export()
        self.root = self.fixture.output
        self.bindings = {
            "expected_" + name: self.pins[name]
            for name in ("candidate_sha256", "manifest_sha256", "protocol_sha256")
        }

    def read(self, **changes):
        return threshold_bundle.verify(self.root, **dict(self.bindings, **changes))

    def test_relocated_bundle_is_verified_without_training_or_execution(self):
        moved = self.root.with_name("relocated")
        self.root.rename(moved)
        self.root = moved
        self.fixture.fixture.blobs.rename(self.root.with_name("unavailable"))
        with patch.object(threshold, "fit", side_effect=AssertionError("must not train")):
            report = self.read()
        self.assertTrue(report["bundle_verified"])
        self.assertTrue(report["artifacts_verified"])
        self.assertEqual(report["candidate_sha256"], self.pins["candidate_sha256"])
        for flag in (
            "rights_verified",
            "signatures_verified",
            "training_verified",
            "preprocessing_verified",
            "qualified",
        ):
            self.assertIs(report[flag], False)
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_external_pins_cannot_be_overridden_by_bundle(self):
        for name in self.bindings:
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"),
            ):
                self.read(**{name: "0" * 64})
        path = self.root / "pins.json"
        original = path.read_bytes()
        for name, value in (
            ("qualified", True),
            ("training_verified", 0),
            ("model_sha256", "0" * 64),
            ("extra", "private marker"),
        ):
            doc = json.loads(original)
            doc[name] = value
            path.write_bytes(json.dumps(doc).encode())
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"),
            ):
                self.read()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
            self.read()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
            self.read()

    def test_metadata_and_blob_substitutions_fail_closed(self):
        paths = [self.root / n for n in ("pins.json", "candidate.json", "manifest.json")]
        paths += [self.root / "blobs" / self.pins[n] for n in ("model_sha256", "search_sha256")]
        for path in paths:
            original = path.read_bytes()
            for kind in ("tamper", "symlink", "fifo", "oversized"):
                path.unlink()
                if kind == "tamper":
                    path.write_bytes(b"private marker")
                elif kind == "symlink":
                    path.symlink_to(self.root / "missing")
                elif kind == "fifo":
                    os.mkfifo(path)
                else:
                    with path.open("wb") as stream:
                        stream.truncate(64 * 1024 * 1024 + 1)
                with (
                    self.subTest(path=path.name, kind=kind),
                    self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"),
                ):
                    self.read()
                path.unlink()
                path.write_bytes(original)
        alias = self.root.with_name("alias")
        alias.symlink_to(self.root, target_is_directory=True)
        for suffix in ("", "/", "/."):
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                threshold_bundle.verify(str(alias) + suffix, **self.bindings)

    def test_pinned_opaque_bytes_must_still_be_a_compatible_scalar_model(self):
        descriptor = json.loads((self.root / "candidate.json").read_bytes())
        model = json.loads(self.fixture.model)
        for kind in ("threshold", "search_binding", "preprocessing_binding"):
            changed = dict(model)
            candidate = dict(descriptor)
            if kind == "threshold":
                changed["threshold"] = 128
            elif kind == "search_binding":
                changed["search_sha256"] = "0" * 64
            else:
                candidate["preprocessing_sha256"] = candidate["rights_sha256"]
            raw = fixtures.fixtures.encode(changed)
            model_pin = fixtures.fixtures.digest(raw)
            (self.root / "blobs" / model_pin).write_bytes(raw)
            candidate["artifact_sha256"] = model_pin
            raw = fixtures.fixtures.encode(candidate)
            candidate_pin = fixtures.fixtures.digest(raw)
            (self.root / "candidate.json").write_bytes(raw)
            pins = dict(self.pins, candidate_sha256=candidate_pin, model_sha256=model_pin)
            (self.root / "pins.json").write_bytes(fixtures.fixtures.encode(pins))
            # A valid generic opaque declaration is insufficient for this format.
            report = fixtures.candidates.verify_artifacts(
                raw,
                self.fixture.fixture.manifest,
                self.root / "blobs",
                **dict(self.bindings, expected_candidate_sha256=candidate_pin),
            )
            self.assertTrue(report["artifacts_verified"])
            with (
                self.subTest(kind=kind),
                self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"),
            ):
                self.read(expected_candidate_sha256=candidate_pin)

    def test_additional_model_and_search_reads_count_against_budget(self):
        report = self.read()
        budget = report["verified_bytes"]
        with patch.object(threshold_bundle, "MAX_TOTAL_BYTES", budget):
            self.assertEqual(self.read()["verified_bytes"], budget)
        with patch.object(threshold_bundle, "MAX_TOTAL_BYTES", budget - 1):
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                self.read()

    def test_cli_is_read_only_and_reports_fixed_errors(self):
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.threshold_bundle_verify",
            str(self.root),
        ]
        for name, value in self.bindings.items():
            command += ["--" + name.removeprefix("expected_").replace("_", "-"), value]
        before = {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        result = subprocess.run(command, capture_output=True, check=False, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["bundle_verified"])
        self.assertEqual(
            before,
            {
                str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob("*")
                if p.is_file()
            },
        )
        (self.root / "pins.json").write_bytes(b"private marker")
        result = subprocess.run(command, capture_output=True, check=False, timeout=10)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr),
            (2, b"", b"invalid_threshold_bundle\n"),
        )
