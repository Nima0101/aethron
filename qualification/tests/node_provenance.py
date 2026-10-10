"""Optional Node probe integration checks; invoked explicitly by the audit job."""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from qualification.tests.test_ingress_audit import changed_corpora

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "qualification/technology/"


class NodeProvenanceTests(unittest.TestCase):
    def test_changed_corpus_prevents_parity_report(self):
        raw = (ROOT / PREFIX / "ingress-vectors-v1.json").read_bytes()
        for label, changed in changed_corpora(raw).items():
            with self.subTest(corpus=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                name = "ingress-probe.mjs"
                (root / name).write_bytes((ROOT / PREFIX / name).read_bytes())
                (root / "ingress-vectors-v1.json").write_bytes(changed)
                result = subprocess.run(
                    ["node", "--v8-pool-size=1", name],
                    cwd=root,
                    env=dict(os.environ, UV_THREADPOOL_SIZE="1"),
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertIn(b"invalid_ingress_corpus", result.stderr)

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
        self.assertEqual(report.get("source_observation"), "equal_before_and_after_workload")
        self.assertIs(report["physical_qualification_passed"], False)

    def changed_source(self, probe, target, *, remove=False):
        # Mutate only disposable copies, after the real experiment has started.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (probe, "ingress-vectors-v1.json"):
                (root / name).write_bytes((ROOT / PREFIX / name).read_bytes())
            original = (root / target).read_bytes()
            operation = "unlinkSync(target)" if remove else "appendFileSync(target, '\\n ')"
            trigger = (
                "const tick = process.hrtime.bigint;\n"
                "process.hrtime.bigint = () => { const result = tick(); mutate(); return result; };"
                if probe == "hash-probe.mjs"
                else "const parse = JSON.parse;\n"
                "JSON.parse = (...args) => { const result = parse(...args); "
                "if (Buffer.isBuffer(args[0])) mutate(); return result; };"
            )
            (root / "driver.mjs").write_text(
                "import { appendFileSync, unlinkSync } from 'node:fs';\n"
                f"const target = new URL({json.dumps('./' + target)}, import.meta.url);\n"
                "let changed = false;\n"
                f"function mutate() {{ if (!changed) {{ changed = true; {operation}; }} }}\n"
                f"{trigger}\n"
                f"await import(new URL({json.dumps('./' + probe)}, import.meta.url));\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["node", "--v8-pool-size=1", "driver.mjs"],
                cwd=root,
                env=dict(os.environ, UV_THREADPOOL_SIZE="1"),
                capture_output=True,
                timeout=15,
                check=False,
            )
            if remove:
                self.assertFalse((root / target).exists(), "mutation did not execute")
            else:
                self.assertNotEqual(
                    (root / target).read_bytes(), original, "mutation did not execute"
                )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
            if not remove:
                self.assertIn(b"probe_sources_changed", result.stderr)

    def test_changed_module_prevents_report(self):
        for probe in ("hash-probe.mjs", "ingress-probe.mjs"):
            with self.subTest(probe=probe):
                self.changed_source(probe, probe)

    def test_changed_vectors_prevent_report(self):
        self.changed_source("ingress-probe.mjs", "ingress-vectors-v1.json")

    def test_removed_sources_prevent_report(self):
        for probe, target in (
            ("hash-probe.mjs", "hash-probe.mjs"),
            ("ingress-probe.mjs", "ingress-probe.mjs"),
            ("ingress-probe.mjs", "ingress-vectors-v1.json"),
        ):
            with self.subTest(probe=probe, target=target):
                self.changed_source(probe, target, remove=True)

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
