"""Generate original synthetic artifacts and consume them through the real CLI."""

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron.evaluation.splits import verify_artifacts


@unittest.skipUnless(
    os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"),
    "POSIX descriptor operations required",
)
class SyntheticDataset(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def generate(self, name="dataset"):
        return importlib.import_module("aethron.evaluation.synthetic").generate(self.root / name)

    def snapshot(self, root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_deterministic_files_and_disjoint_content_are_verifiable(self):
        pins = self.generate()
        self.assertEqual(pins, self.generate("second"))
        self.assertEqual(self.snapshot(self.root / "dataset"), self.snapshot(self.root / "second"))
        root = self.root / "dataset"
        self.assertEqual(pins, json.loads((root / "pins.json").read_bytes()))
        raw = (root / "manifest.json").read_bytes()
        self.assertEqual(pins["manifest_sha256"], hashlib.sha256(raw).hexdigest())
        result = verify_artifacts(raw, root / "blobs")
        self.assertEqual(result["counts"], {"train": 3, "validation": 3, "test": 3})
        self.assertEqual(result["verified_blobs"], 12)
        self.assertFalse(pins["qualified"])
        self.assertFalse(pins["rights_verified"])
        self.assertEqual(pins["evidence"], "synthetic")
        doc = json.loads(raw)
        for split in ("train", "validation", "test"):
            selected = [r for r in doc["samples"] if r["split"] == split]
            other = [r for r in doc["samples"] if r["split"] != split]
            for key in ("source_sha256", "artifact_sha256", "session_sha256"):
                self.assertTrue({r[key] for r in selected}.isdisjoint({r[key] for r in other}))
            annotation = (root / f"annotations-{split}.json").read_bytes()
            self.assertEqual(
                pins["annotations_sha256"][split], hashlib.sha256(annotation).hexdigest()
            )
            self.assertEqual(json.loads(annotation)["manifest_sha256"], pins["manifest_sha256"])

    def test_existing_directory_file_or_symlink_is_never_overwritten(self):
        target = self.root / "existing"
        target.mkdir()
        sentinel = target / "sentinel"
        sentinel.write_bytes(b"keep")
        (self.root / "link").symlink_to(target, target_is_directory=True)
        (self.root / "file").write_bytes(b"keep file")
        (self.root / "empty").mkdir()
        for name in ("existing", "link", "file", "empty"):
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(ValueError, "^invalid_fixture_output$"),
            ):
                self.generate(name)
        self.assertEqual(list(target.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertEqual((self.root / "file").read_bytes(), b"keep file")
        self.assertEqual(list((self.root / "empty").iterdir()), [])

    def test_interrupted_output_has_no_completion_pins(self):
        api = importlib.import_module("aethron.evaluation.synthetic")
        original_open = os.open

        def fail_manifest(path, *args, **kwargs):
            if path == "manifest.json":
                raise OSError("simulated storage failure")
            return original_open(path, *args, **kwargs)

        with patch.object(api.os, "open", fail_manifest):
            with self.assertRaisesRegex(ValueError, "^invalid_fixture_output$"):
                self.generate()
        self.assertEqual(len(list((self.root / "dataset" / "blobs").iterdir())), 12)
        self.assertFalse((self.root / "dataset" / "pins.json").exists())
        with self.assertRaisesRegex(ValueError, "^invalid_fixture_output$"):
            self.generate()

    def test_partial_pins_write_is_not_published(self):
        api = importlib.import_module("aethron.evaluation.synthetic")
        original_write = api._write

        def interrupt_pins(directory_fd, name, data):
            if b'"annotations_sha256"' in data:
                original_write(directory_fd, name, data[:20])
                raise OSError("simulated interrupted pins write")
            original_write(directory_fd, name, data)

        with patch.object(api, "_write", interrupt_pins):
            with self.assertRaisesRegex(ValueError, "^invalid_fixture_output$"):
                self.generate()
        self.assertTrue((self.root / "dataset" / "manifest.json").is_file())
        self.assertFalse((self.root / "dataset" / "pins.json").exists())

    def test_generator_and_comparison_clis_retain_matches_misses_and_false_positives(self):
        output = self.root / "from-cli"
        command = [sys.executable, "-m", "aethron.evaluation.synthetic", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        pins = json.loads(result.stdout)
        for split in ("train", "validation", "test"):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aethron.evaluation.proposals",
                    str(output / "manifest.json"),
                    "--blob-dir",
                    str(output / "blobs"),
                    "--split",
                    split,
                    "--baseline",
                    "all",
                    "--manifest-sha256",
                    pins["manifest_sha256"],
                    "--protocol-sha256",
                    pins["protocol_sha256"],
                    "--annotations",
                    str(output / f"annotations-{split}.json"),
                    "--annotations-sha256",
                    pins["annotations_sha256"][split],
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            reports = json.loads(result.stdout)["reports"]
            self.assertEqual(
                [r["metrics"] for r in reports],
                [
                    {
                        "true_positives": 1,
                        "false_positives": 0,
                        "false_negatives": 1,
                        "precision": 1.0,
                        "recall": 0.5,
                    },
                    {
                        "true_positives": 1,
                        "false_positives": 1,
                        "false_negatives": 1,
                        "precision": 0.5,
                        "recall": 0.5,
                    },
                ],
            )
            self.assertEqual(
                [r["evidence_counts"] for r in reports], [{"synthetic": 3, "recorded": 0}] * 2
            )
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "invalid_fixture_output")
