"""Optional Node probe integration checks; invoked explicitly by the audit job."""

import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "qualification/technology/"


class NodeProvenanceTests(unittest.TestCase):
    def probe(self, name):
        result = subprocess.run(
            ["node", "--v8-pool-size=1", PREFIX + name],
            cwd=ROOT,
            env=dict(os.environ, UV_THREADPOOL_SIZE="1"),
            capture_output=True,
            timeout=15,
            check=True,
        )
        self.assertEqual(result.stderr, b"")
        return json.loads(result.stdout)

    def bindings(self, report, names):
        self.assertEqual(
            report.get("source_sha256"),
            {
                PREFIX + name: hashlib.sha256((ROOT / PREFIX / name).read_bytes()).hexdigest()
                for name in names
            },
        )
        self.assertEqual(report.get("audit_policy_version"), 3)
        self.assertIs(report["physical_qualification_passed"], False)

    def test_ingress_binds_source_and_vectors_without_erasing_negatives(self):
        report = self.probe("ingress-probe.mjs")
        self.assertIs(report["parity"], False)
        self.assertEqual(
            [row["id"] for row in report["cases"] if not row["matches"]],
            ["duplicate-equal", "duplicate-overwrite", "duplicate-escaped", "nested-duplicate"],
        )
        self.assertEqual(len(report["cases"]), 18)
        self.bindings(report, ("ingress-probe.mjs", "ingress-vectors-v1.json"))

    def test_hash_probe_binds_source_without_changing_known_vectors(self):
        report = self.probe("hash-probe.mjs")
        self.assertEqual(
            report["known_vectors"],
            [
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            ],
        )
        self.assertIs(report["alias_changed"], True)
        self.assertIs(report["owned_preserved"], True)
        self.bindings(report, ("hash-probe.mjs",))


if __name__ == "__main__":
    unittest.main()
