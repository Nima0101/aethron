"""Contract probes for technology migration; never hardware qualification."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.evidence import validate
from qualification.technology import compare_ingress


def changed_corpora(raw):
    vectors = json.loads(raw)
    duplicate = vectors[:-1] + [vectors[0]]
    rewritten = json.loads(raw)
    rewritten[9]["hex"] = vectors[0]["hex"]
    expectations = json.loads(raw)
    for row in expectations:
        if "duplicate" in row["id"]:
            row["reject"] = False
    return {
        name: json.dumps(rows).encode()
        for name, rows in (
            ("empty", []),
            ("missing", [row for row in vectors if "duplicate" not in row["id"]]),
            ("duplicate", duplicate),
            ("rewritten_bytes", rewritten),
            ("erased_negative_expectations", expectations),
        )
    }


class IngressAuditTests(unittest.TestCase):
    def test_changed_corpus_blocks_export_and_comparison(self):
        vector_path = Path(compare_ingress.__file__).parent / "ingress-vectors-v1.json"
        read_bytes, read_text = Path.read_bytes, Path.read_text
        for label, changed in changed_corpora(vector_path.read_bytes()).items():
            requests = [(bytes.fromhex(row["hex"]), 1050) for row in json.loads(changed)]
            requests += compare_ingress.collect()
            responses = []
            for raw, now_ms in requests:
                row = {"accepted": False}
                if "error" not in compare_ingress.outcome(raw, now_ms):
                    row = {"accepted": True, "document": json.loads(raw)}
                responses.append(json.dumps(row))
            for export in (False, True):
                with self.subTest(corpus=label, export=export):
                    with tempfile.TemporaryDirectory() as directory:
                        path = Path(directory) / "synthetic-responses.jsonl"
                        path.write_text("\n".join(responses) + "\n", encoding="utf-8")
                        argv = (
                            ["probe", "--export"] if export else ["probe", "--responses", str(path)]
                        )
                        output = io.StringIO()
                        with (
                            patch("sys.argv", argv),
                            patch.object(
                                Path,
                                "read_bytes",
                                lambda p, data=changed: data if p == vector_path else read_bytes(p),
                            ),
                            patch.object(
                                Path,
                                "read_text",
                                lambda p, *a, data=changed, **k: (
                                    data.decode() if p == vector_path else read_text(p, *a, **k)
                                ),
                            ),
                            patch.object(
                                compare_ingress, "collect", wraps=compare_ingress.collect
                            ) as collect,
                            contextlib.redirect_stdout(output),
                        ):
                            with self.assertRaisesRegex(RuntimeError, "^invalid_ingress_corpus$"):
                                compare_ingress.main()
                        self.assertEqual(output.getvalue(), "")
                        collect.assert_not_called()

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
