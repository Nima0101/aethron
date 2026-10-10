"""P16 consumes published P2 raw packet APIs; authentication is not qualification."""

import base64
import hashlib
import json
import unittest
from pathlib import Path

from aethron_edge.sensors import packets

from aethron.interop_bundles import verify_task_bundle

ROOT = Path(__file__).resolve().parents[2]


class SensorPacketConformance(unittest.TestCase):
    def encoding_vectors(self):
        path = ROOT / "examples/interop/sensor-encoding-vectors-v1.json"
        self.assertTrue(path.is_file(), "missing byte-order/padding conformance corpus")
        return json.loads(path.read_bytes())

    def test_encoding_corpus_binds_original_source_and_case_inventory(self):
        vectors = self.encoding_vectors()
        original = ROOT / "examples/interop/sensor-packet-vectors-v1.json"
        self.assertEqual(vectors["version"], 1)
        self.assertEqual(vectors["base_case"], "synthetic-depth")
        self.assertEqual(
            vectors["base_corpus_sha256"], hashlib.sha256(original.read_bytes()).hexdigest()
        )
        self.assertEqual(vectors["source_commit"], self.vectors()["source_commit"])
        self.assertEqual(vectors["source_sha256"], self.vectors()["source_sha256"])
        self.assertEqual(
            [case["name"] for case in vectors["cases"]],
            [
                "equivalent-big-endian",
                "changed-byte-order",
                "equivalent-row-padding",
                "trailing-byte",
            ],
        )

        self.assertEqual(
            [(case["decode_error"], case["depth_m"]) for case in vectors["cases"]],
            [(None, 5.0), (None, 100.37), (None, 5.0), ("invalid_image_bytes", None)],
        )

    def test_decodable_encoding_changes_cannot_reuse_original_authentication(self):
        vectors = self.encoding_vectors()
        original = self.vectors()["cases"][0]
        self.assertEqual(self.bind(original).status, "bound")
        for case in vectors["cases"]:
            with self.subTest(case=case["name"]):
                layout_bytes, pixel_bytes = map(bytes.fromhex, case["evidence_hex"])
                self.assertNotEqual(case["evidence_hex"], original["evidence_hex"])
                if case["decode_error"] is None:
                    raster = packets.decode_image(json.loads(layout_bytes), pixel_bytes)
                    self.assertIsNone(raster.depth_m(0, 0))
                    self.assertAlmostEqual(raster.depth_m(1, 0), case["depth_m"])
                else:
                    with self.assertRaisesRegex(ValueError, "^invalid_image_bytes$"):
                        packets.decode_image(json.loads(layout_bytes), pixel_bytes)
                result = self.bind(dict(original, evidence_hex=case["evidence_hex"]))
                self.assertEqual((result.status, result.reason), ("rejected", "evidence_mismatch"))
                self.assertEqual(result.evidence, ())
                self.assertIsNone(result.task_sha256)
                self.assertIsNone(result.passport_sha256)
                self.assertIsNone(result.policy_revision)
                self.assertIsNone(result.expires_at)

    def vectors(self):
        path = ROOT / "examples/interop/sensor-packet-vectors-v1.json"
        self.assertTrue(path.is_file(), "missing portable P2/P16 conformance corpus")
        return json.loads(path.read_bytes())

    def bind(self, case):
        result = verify_task_bundle(
            *(case[key].encode() for key in ("task", "envelope", "policy")),
            tuple(bytes.fromhex(value) for value in case["evidence_hex"]),
            **case["arguments"],
        )
        self.assertIs(result.motion_authority, False)
        self.assertIs(result.execution_authority, False)
        self.assertIs(result.evidence_verified, False)
        return result

    def test_published_producer_source_and_actual_import_match(self):
        vectors = self.vectors()
        expected = {
            "integrations/edge/aethron_edge/sensors/packets.py": "56d66f258b24f8cf4d4af9a1b1328a1bbaf326b839e5edf08f3a5327ff281192",
            "integrations/edge/aethron_edge/__init__.py": "fc3adf2bb0f73d7339bc54e6d0fb2f94c5dc53a2946bac32856cf5f01b61faa9",
            "integrations/edge/aethron_edge/sensors/__init__.py": "98905b1b18d58ff7bcee36a3854f2022be6443c0b36c4217f4f5781197f8d92a",
        }
        self.assertEqual(vectors["source_commit"], "a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46")
        self.assertEqual(vectors["source_sha256"], expected)
        for path, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        self.assertEqual(
            Path(packets.__file__).resolve(),
            ROOT / "integrations/edge/aethron_edge/sensors/packets.py",
        )

    def test_real_binding_preserves_every_portable_outcome(self):
        cases = self.vectors()["cases"]
        self.assertEqual(
            [c["name"] for c in cases],
            [
                "synthetic-depth",
                "substituted-layout",
                "altered-pixels",
                "signed-truncated-pixels",
                "signed-missing-depth",
            ],
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                result = self.bind(case)
                self.assertEqual((result.status, result.reason), (case["status"], case["reason"]))
                self.assertEqual([ref.outcome for ref in result.evidence], case["outcomes"])
                if result.status == "bound":
                    self.assertEqual(result.expires_at, 1700)
                    self.assertEqual([ref.kind for ref in result.evidence], ["synthetic"] * 2)
                    self.assertEqual(
                        {ref.sha256 for ref in result.evidence},
                        {
                            hashlib.sha256(bytes.fromhex(b)).hexdigest()
                            for b in case["evidence_hex"]
                        },
                    )
                else:
                    self.assertIsNone(result.task_sha256)
                    self.assertIsNone(result.passport_sha256)
                    self.assertIsNone(result.expires_at)
                    self.assertEqual(result.evidence, ())

    def test_layout_and_payload_are_both_bound(self):
        original, changed_layout, changed_pixels = self.vectors()["cases"][:3]
        layout_bytes, pixel_bytes = map(bytes.fromhex, original["evidence_hex"])
        self.assertEqual(pixel_bytes, b"\x00\x00\xc4\x09")
        layout = json.loads(layout_bytes)
        raster = packets.decode_image(layout, pixel_bytes)
        self.assertIsNone(raster.depth_m(0, 0))
        self.assertEqual(raster.depth_m(1, 0), 5.0)
        self.assertEqual(self.bind(original).status, "bound")
        changed = json.loads(bytes.fromhex(changed_layout["evidence_hex"][0]))
        self.assertEqual(changed, dict(layout, meters_per_unit=0.004))
        self.assertEqual(changed_layout["evidence_hex"][1], original["evidence_hex"][1])
        self.assertEqual(packets.decode_image(changed, pixel_bytes).depth_m(1, 0), 10.0)
        self.assertEqual(self.bind(changed_layout).reason, "evidence_mismatch")
        self.assertEqual(changed_pixels["evidence_hex"][0], original["evidence_hex"][0])
        self.assertNotEqual(changed_pixels["evidence_hex"][1], original["evidence_hex"][1])
        self.assertEqual(self.bind(changed_pixels).reason, "evidence_mismatch")

    def test_signed_malformed_payload_is_not_sensor_validation(self):
        case = self.vectors()["cases"][3]
        layout_bytes, pixel_bytes = map(bytes.fromhex, case["evidence_hex"])
        self.assertEqual(pixel_bytes, b"\x00\x00\xc4")
        result = self.bind(case)
        self.assertEqual(result.status, "bound")
        self.assertEqual([ref.outcome for ref in result.evidence], ["failed", "failed"])
        with self.assertRaisesRegex(ValueError, "^invalid_image_bytes$"):
            packets.decode_image(json.loads(layout_bytes), pixel_bytes)
        statement = json.loads(base64.b64decode(json.loads(case["envelope"])["payload"]))
        self.assertEqual([c["name"] for c in statement["capabilities"]], ["evidence.offline.v1"])

    def test_signed_zero_depth_remains_unknown(self):
        case = self.vectors()["cases"][4]
        layout_bytes, pixel_bytes = map(bytes.fromhex, case["evidence_hex"])
        self.assertEqual(pixel_bytes, b"\x00" * 4)
        result = self.bind(case)
        self.assertEqual(result.status, "bound")
        self.assertEqual([ref.outcome for ref in result.evidence], ["unknown", "unknown"])
        raster = packets.decode_image(json.loads(layout_bytes), pixel_bytes)
        self.assertIsNone(raster.depth_m(0, 0))
        self.assertIsNone(raster.depth_m(1, 0))


if __name__ == "__main__":
    unittest.main()
