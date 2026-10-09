"""Contract probes for technology migration; never hardware qualification."""

import hashlib
import json
import unittest
from pathlib import Path

from qualification.evidence import validate


class IngressAuditTests(unittest.TestCase):
    def test_portable_vectors_preserve_wire_rejections_and_byte_commitments(self):
        vector_path = Path(__file__).parents[1] / "technology" / "ingress-vectors-v1.json"
        self.assertTrue(vector_path.is_file(), "portable ingress audit vectors are missing")
        vectors = json.loads(vector_path.read_text())
        self.assertGreater(len(vectors), 10)
        for vector in vectors:
            with self.subTest(case=vector["id"]):
                payload = bytes.fromhex(vector["hex"])
                if vector["reject"]:
                    with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                        validate(payload, now_ms=1050)
                else:
                    report = validate(payload, now_ms=1050)
                    self.assertEqual(report["input_sha256"], hashlib.sha256(payload).hexdigest())
                    self.assertEqual(report["findings"], vector["findings"])
                    self.assertFalse(report["physical_qualification_passed"])


if __name__ == "__main__":
    unittest.main()
