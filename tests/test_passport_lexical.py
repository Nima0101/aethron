"""Portable byte-level cases for parser technology conformance."""

import json
import unittest
from hashlib import sha256
from pathlib import Path

from aethron.passports import canonicalize

CORPUS = Path(__file__).resolve().parents[1] / "examples/passports/parser-vectors-v1.json"


class ParserLexicalConformance(unittest.TestCase):
    def test_portable_lexical_cases(self):
        self.assertTrue(CORPUS.is_file(), "portable lexical corpus missing")
        raw_corpus = CORPUS.read_bytes()
        self.assertEqual(
            sha256(raw_corpus).hexdigest(),
            "1be832f5b9d0120c3dab3816f72c679081ffbdc5b81d38efdb3432fe23922ced",
        )
        cases = json.loads(raw_corpus)["cases"]
        self.assertEqual(len(cases), 14)
        self.assertEqual(len({case["name"] for case in cases}), 14)
        for case in cases:
            with self.subTest(case=case["name"]):
                raw = bytes.fromhex(case["input_hex"])
                if case["canonical_hex"] is None:
                    with self.assertRaisesRegex(ValueError, "^invalid_passport$"):
                        canonicalize(raw)
                else:
                    self.assertEqual(canonicalize(raw), bytes.fromhex(case["canonical_hex"]))


if __name__ == "__main__":
    unittest.main()
