"""Original synthetic model-card declarations; matching metadata grants no rights."""

import copy
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_candidate_holdout as fixtures

from aethron.evaluation.splits import _filesystem_supported


class CandidateCards(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.CandidateHoldout()
        fixture.setUp()
        self.candidate = fixture.candidate
        self.manifest = fixtures.encode(fixture.training)
        self.card = {
            "version": 1,
            "task": "obstacle_proposals",
            "format": "opaque",
            "format_version": "fixture-v1",
            "source": "Original synthetic opaque bytes",
            "origin": "AETHRON test fixture",
            "license": "GPL-3.0-only",
            "intended_use": "offline_obstacle_evaluation",
            "forbidden_uses": [
                "biometric_identity",
                "cross_scene_reidentification",
                "person_history",
                "targeting",
                "weapons",
                "autonomous_pursuit",
                "live_safety",
            ],
            "reproducibility": "Generate synthetic fixtures; never execute opaque bytes.",
            "limitations": ["Synthetic software fixture only; no physical qualification."],
        }
        for field in (
            "artifact_sha256",
            "preprocessing_sha256",
            "protocol_sha256",
            "training_manifest_sha256",
            "rights_sha256",
        ):
            self.card[field] = self.candidate[field]

    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron.evaluation.cards"), "card gate missing"
        )
        return importlib.import_module("aethron.evaluation.cards")

    def inputs(self, raw=None):
        raw = fixtures.encode(self.card) if raw is None else raw
        self.candidate["card_sha256"] = fixtures.sha(raw)
        candidate = fixtures.encode(self.candidate)
        pins = {
            "expected_candidate_sha256": fixtures.sha(candidate),
            "expected_manifest_sha256": fixtures.sha(self.manifest),
            "expected_protocol_sha256": self.candidate["protocol_sha256"],
        }
        return raw, candidate, pins

    def run_card(self, raw=None):
        raw, candidate, pins = self.inputs(raw)
        return self.api().validate(raw, candidate, self.manifest, **pins)

    def test_bound_card_exports_only_bindings_and_unverified_claims(self):
        result = self.run_card()
        self.assertEqual(result["card_sha256"], fixtures.sha(fixtures.encode(self.card)))
        self.assertEqual(result["artifact_sha256"], self.candidate["artifact_sha256"])
        self.assertTrue(result["card_structure_valid"])
        for key in ("rights_verified", "training_verified", "artifacts_verified", "qualified"):
            self.assertIs(result[key], False)
        for private_text in (
            self.card["source"],
            self.card["origin"],
            self.card["reproducibility"],
        ):
            self.assertNotIn(private_text, json.dumps(result))

    def test_all_five_candidate_references_must_match(self):
        for key in (
            "artifact_sha256",
            "preprocessing_sha256",
            "protocol_sha256",
            "training_manifest_sha256",
            "rights_sha256",
        ):
            original = self.card[key]
            self.card[key] = "0" * 64
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_card$"),
            ):
                self.run_card()
            self.card[key] = original

    def test_unbound_card_and_wrong_caller_pins_reject(self):
        raw, candidate, pins = self.inputs()
        with self.assertRaisesRegex(ValueError, "^invalid_candidate_card$"):
            self.api().validate(raw + b" ", candidate, self.manifest, **pins)
        for key in pins:
            for value in (True, None, "0" * 64):
                changed = dict(pins, **{key: value})
                with (
                    self.subTest(key=key, value=value),
                    self.assertRaisesRegex(ValueError, "^invalid_candidate_card$"),
                ):
                    self.api().validate(raw, candidate, self.manifest, **changed)

    def test_required_metadata_and_closed_fields(self):
        original = copy.deepcopy(self.card)
        for key in original:
            self.card = copy.deepcopy(original)
            del self.card[key]
            with (
                self.subTest(missing=key),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_card$"),
            ):
                self.run_card()
        for key, value in (
            ("approved", True),
            ("version", True),
            ("version", 2),
            ("task", "person_identity"),
            ("format", "pickle"),
            ("intended_use", "live_safety"),
            ("format_version", "../x"),
            ("source", ""),
            ("license", " "),
            ("origin", ["author"]),
            ("reproducibility", "x" * 513),
            ("source", "private\nvalue"),
            ("origin", "hidden\u0085line"),
            ("source", "\ud800"),
            ("limitations", []),
            ("limitations", [""]),
            ("limitations", ["same", "same"]),
            ("limitations", list(map(str, range(17)))),
        ):
            self.card = copy.deepcopy(original)
            self.card[key] = value
            with (
                self.subTest(key=key, value=value),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_card$"),
            ):
                self.run_card()

    def test_all_forbidden_uses_required_once_in_any_order(self):
        uses = self.card["forbidden_uses"][:]
        for value in (
            uses[:-1],
            uses + [uses[0]],
            uses + ["unknown"],
            "weapons",
            [None],
            [["weapons"]],
        ):
            self.card["forbidden_uses"] = value
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_card$"),
            ):
                self.run_card()
        self.card["forbidden_uses"] = list(reversed(uses))
        self.assertTrue(self.run_card()["card_structure_valid"])

    def test_strict_json_and_exact_card_byte_bound(self):
        valid = fixtures.encode(self.card)
        padded = valid.ljust(16384, b" ")
        self.assertTrue(self.run_card(padded)["card_structure_valid"])
        for raw in (
            padded + b" ",
            b"null",
            b"NaN",
            b"\xff",
            bytearray(valid),
            valid[:-1] + b',"version":1}',
            b"[" * 9 + b"]" * 9,
        ):
            with (
                self.subTest(kind=type(raw)),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_card$"),
            ):
                self.run_card(raw)

    @unittest.skipUnless(_filesystem_supported(), "POSIX required")
    def test_cli_rejects_tampered_card_without_metadata_output(self):
        raw, candidate, pins = self.inputs()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "card").write_bytes(raw)
            (root / "candidate").write_bytes(candidate)
            (root / "manifest").write_bytes(self.manifest)
            command = [
                sys.executable,
                "-m",
                "aethron.evaluation.cards",
                str(root / "card"),
                "--candidate",
                str(root / "candidate"),
                "--training-manifest",
                str(root / "manifest"),
            ]
            for key, value in pins.items():
                command.extend(["--" + key.removeprefix("expected_").replace("_", "-"), value])
            good = subprocess.run(command, capture_output=True, timeout=10, check=False)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(json.loads(good.stdout), self.run_card())
            (root / "card").write_bytes(b"private unbound metadata")
            bad = subprocess.run(command, capture_output=True, timeout=10, check=False)
            self.assertEqual(
                (bad.returncode, bad.stdout, bad.stderr), (2, b"", b"invalid_candidate_card\n")
            )
