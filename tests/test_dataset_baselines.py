"""Original pixel fixtures comparing fixed-threshold and local-contrast baselines."""

import hashlib
import importlib
import json
import random
import subprocess
import sys
import tracemalloc
import unittest
from unittest.mock import patch

import test_dataset_metrics as fixtures

LOCAL = "classical_pgm_obstacle_v1"
GLOBAL = "global_pgm_obstacle_v1"


def pgm(width, height, pixels):
    return f"P5\n{width} {height}\n255\n".encode() + bytes(pixels)


class GlobalPixels(unittest.TestCase):
    def detect(self, data):
        return importlib.import_module("aethron.evaluation.baselines").detect_global_pgm(data)

    def test_threshold_and_component_size_boundaries(self):
        for pixels, count in (
            ([127] * 3, 1),
            ([128] * 3, 0),
            ([0] * 2, 0),
            ([0] * 1200, 1),
            ([0] * 1201, 0),
        ):
            width = 3 if len(pixels) == 1200 else 1
            height = len(pixels) // width
            # 1201 pixels remain within the existing640x512 decoder bounds.
            if len(pixels) == 1201:
                pixels = [0] * 1201 + [255] * (40 * 31 - 1201)
                width, height = 40, 31
            with self.subTest(count=count, size=len(pixels)):
                self.assertEqual(len(self.detect(pgm(width, height, pixels))), count)

    def test_diagonal_connectivity_and_normalized_extent(self):
        data = pgm(3, 3, [0, 255, 255, 255, 0, 255, 255, 255, 0])
        self.assertEqual(
            self.detect(data),
            [
                {
                    "class": "obstacle",
                    "box": [0.0, 0.0, 1.0, 1.0],
                    "score": 0.6,
                    "variance": 0.0001,
                    "range_m": None,
                }
            ],
        )
        for data in (b"bad", b"P5\n3 3\n255\nshort"):
            with self.assertRaises(ValueError):
                self.detect(data)

    def test_component_limit_and_ties_are_deterministic(self):
        # 33 isolated vertical3-pixel components; keep first32 by normalized box order.
        pixels = [255] * (99 * 3)
        for x in range(0, 99, 3):
            for y in range(3):
                pixels[y * 99 + x] = 0
        result = self.detect(pgm(99, 3, pixels))
        self.assertEqual(len(result), 32)
        self.assertEqual(result[0]["box"], [0.0, 0.0, 1 / 99, 1.0])
        self.assertEqual(result[-1]["box"], [93 / 99, 0.0, 1 / 99, 1.0])
        self.assertEqual(result, self.detect(pgm(99, 3, pixels)))

    def test_many_components_preserve_late_largest_and_box_ties_with_bounded_memory(self):
        width, height = 640, 256
        pixels = [255] * (width * height)
        for y in range(0, 252, 4):
            for x in range(0, width, 4):
                for yy in range(y, y + 3):
                    pixels[yy * width + x] = 0
        # Last in scan order, first by component size; ties then sort x before y.
        pixels[-4:] = [0] * 4
        data = pgm(width, height, pixels)
        detect = importlib.import_module("aethron.evaluation.baselines").detect_global_pgm
        tracemalloc.start()
        try:
            result = detect(data)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        boxes = [[636 / width, 255 / height, 4 / width, 1 / height]]
        boxes.extend([[0.0, y / height, 1 / width, 3 / height] for y in range(0, 124, 4)])
        self.assertEqual(
            result,
            [
                {"class": "obstacle", "box": box, "score": 0.6, "variance": 0.0001, "range_m": None}
                for box in boxes
            ],
        )
        self.assertLess(peak, 2 * 1024 * 1024, f"traced peak: {peak} bytes")

    def test_seeded_rectangles_match_independent_full_ranking(self):
        rng = random.Random(472)
        for case in range(40):
            pixels = [255] * (64 * 64)
            rectangles = []
            for y in range(0, 64, 8):
                for x in range(0, 64, 8):
                    width, height = rng.randint(1, 6), rng.randint(1, 6)
                    for yy in range(y, y + height):
                        pixels[yy * 64 + x : yy * 64 + x + width] = [0] * width
                    if width * height >= 3:
                        rectangles.append(
                            (width * height, [x / 64, y / 64, width / 64, height / 64])
                        )
            expected = sorted(rectangles, key=lambda item: (-item[0], item[1]))[:32]
            with self.subTest(case=case):
                result = self.detect(pgm(64, 64, pixels))
                self.assertEqual([row["box"] for row in result], [box for _, box in expected])


@unittest.skipIf(getattr(fixtures.DatasetMetrics, "__unittest_skip__", False), "POSIX required")
class DatasetBaselines(unittest.TestCase):
    def setUp(self):
        self.labels = fixtures.DatasetMetrics()
        self.labels.setUp()
        self.addCleanup(self.labels.doCleanups)
        # Uniform dark frame: global threshold proposes entire frame; local contrast none.
        self.labels.images.image(2, pgm(8, 8, [100] * 64))
        self.labels.doc["manifest_sha256"] = hashlib.sha256(self.labels.fixture.raw()).hexdigest()
        self.labels.doc["samples"][0].update(
            artifact_sha256=self.labels.fixture.doc["samples"][2]["artifact_sha256"], boxes=[]
        )

    def run_baseline(self, baseline):
        raw = json.dumps(self.labels.doc).encode()
        return self.labels.images.run_baseline(
            baseline=baseline,
            annotations=raw,
            expected_annotations_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def test_explicit_baseline_and_same_snapshot_comparison(self):
        local, global_ = self.run_baseline(LOCAL), self.run_baseline(GLOBAL)
        self.assertEqual(local["proposal_count"], 0)
        self.assertEqual(global_["proposal_count"], 1)
        self.assertEqual(global_["metrics"]["false_positives"], 1)
        self.assertEqual(global_["baseline"], GLOBAL)
        report = self.run_baseline("all")
        self.assertEqual(report["reports"], [local, global_])
        self.assertFalse(report["qualified"])
        self.assertFalse(report["rights_verified"])
        # Replace blob during first detector call: both detectors must use retained bytes.
        api = importlib.import_module("aethron.evaluation.proposals")
        original = api.detect_pgm
        path = self.labels.fixture.root / self.labels.fixture.doc["samples"][2]["artifact_sha256"]

        def replace_after_load(data):
            path.write_bytes(pgm(8, 8, [255] * 64))
            return original(data)

        with patch.object(api, "detect_pgm", replace_after_load):
            self.assertEqual(self.run_baseline("all"), report)
        with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
            self.run_baseline("all")

    def test_counts_only_comparison_does_not_claim_accuracy(self):
        report = self.labels.images.run_baseline(baseline="all")
        self.assertEqual([r["proposal_count"] for r in report["reports"]], [0, 1])
        for result in report["reports"]:
            self.assertFalse(result["accuracy_evaluated"])
            self.assertNotIn("metrics", result)
            self.assertEqual(result["evidence_counts"], {"synthetic": 1, "recorded": 0})

    def test_unknown_baseline_rejects_before_blob_access(self):
        # A nonexistent root must not mask an invalid baseline selection.
        api = importlib.import_module("aethron.evaluation.proposals")
        for baseline in ("private-unknown", None, [], True):
            with (
                self.subTest(baseline=baseline),
                self.assertRaisesRegex(ValueError, "^invalid_proposal_input$"),
            ):
                api.run(
                    b"bad",
                    "/does-not-exist",
                    "test",
                    expected_manifest_sha256="0" * 64,
                    expected_protocol_sha256="0" * 64,
                    baseline=baseline,
                )

    def test_cli_compares_then_rejects_malformed_image_without_partial_report(self):
        root = self.labels.fixture.root
        manifest = root.parent / "manifest.json"
        annotation = root.parent / "annotations.json"
        raw = json.dumps(self.labels.doc).encode()
        manifest.write_bytes(self.labels.fixture.raw())
        annotation.write_bytes(raw)
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.proposals",
            str(manifest),
            "--blob-dir",
            str(root),
            "--split",
            "test",
            "--baseline",
            "all",
            "--manifest-sha256",
            self.labels.doc["manifest_sha256"],
            "--protocol-sha256",
            self.labels.doc["protocol_sha256"],
            "--annotations",
            str(annotation),
            "--annotations-sha256",
            hashlib.sha256(raw).hexdigest(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [r["proposal_count"] for r in json.loads(result.stdout)["reports"]], [0, 1]
        )
        self.labels.images.image(2, b"private malformed PGM")
        self.labels.doc["manifest_sha256"] = hashlib.sha256(self.labels.fixture.raw()).hexdigest()
        self.labels.doc["samples"][0]["artifact_sha256"] = self.labels.fixture.doc["samples"][2][
            "artifact_sha256"
        ]
        raw = json.dumps(self.labels.doc).encode()
        annotation.write_bytes(raw)
        manifest.write_bytes(self.labels.fixture.raw())
        command[command.index("--manifest-sha256") + 1] = self.labels.doc["manifest_sha256"]
        command[command.index("--annotations-sha256") + 1] = hashlib.sha256(raw).hexdigest()
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "invalid_proposal_input")
