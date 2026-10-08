"""Frozen tracking metrics, pixel-to-track recorded replay, and resource regression gates."""

import argparse
import hashlib
import io
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rescuesense.temporal import Session  # noqa: E402 - source-checkout entry point
from rescuesense.temporal.fixtures import (  # noqa: E402 - source-checkout entry point
    detection,
    encode,
    frame,
)
from rescuesense.temporal.fusion import observations  # noqa: E402 - source-checkout entry point
from rescuesense.temporal.math import (  # noqa: E402 - source-checkout entry point
    assignment,
    centre,
    iou,
)
from rescuesense.temporal.pixels import detect_pgm  # noqa: E402 - source-checkout entry point
from rescuesense.temporal.registration import estimate_translation  # noqa: E402
from rescuesense.temporal.replay import replay  # noqa: E402 - source-checkout entry point


class Greedy:
    """Independent no-motion IoU baseline, with identical score and age limits."""

    def __init__(self):
        self.tracks = []
        self.serial = 0

    def step(self, f):
        at = f["at_ms"]
        self.tracks = [t for t in self.tracks if at - t["last"] <= 500 and at - t["born"] < 10000]
        if f["scene_break"]:
            self.tracks = []
        ds, _ = observations(f, at)
        pairs = sorted(
            (-iou(t["box"], d["box"]), i, j)
            for i, t in enumerate(self.tracks)
            for j, d in enumerate(ds)
            if t["class"] == d["class"]
        )
        used_t, used_d = set(), set()
        for negative, i, j in pairs:
            if -negative < 0.3 or i in used_t or j in used_d:
                continue
            t = self.tracks[i]
            d = ds[j]
            t.update(box=d["box"], last=at)
            used_t.add(i)
            used_d.add(j)
        for j, d in enumerate(ds):
            if j not in used_d and d["score"] >= 0.6 and len(self.tracks) < 32:
                self.serial += 1
                self.tracks.append(dict(d, id=str(self.serial), last=at, born=at))
        return {"tracks": [dict(t, status="PRESENT") for t in self.tracks if t["last"] == at]}


def metrics(entries, results):
    tp = fp = fn = switches = fragments = predictions = 0
    squared = 0.0
    last_ids, last_frames = {}, {}
    for index, (entry, result) in enumerate(zip(entries, results)):
        gt = entry["truth"]
        preds = [t for t in result["tracks"] if t["status"] == "PRESENT"]
        predictions += sum(t["status"] != "PRESENT" for t in result["tracks"])
        costs = []
        for g in gt:
            costs.append(
                [
                    1 - iou(g["box"], p["box"])
                    if g["class"] == p["class"] and iou(g["box"], p["box"]) >= 0.3
                    else 1000.0
                    for p in preds
                ]
                + [1.1] * len(gt)
            )
        matches = [(i, j) for i, j in assignment(costs) if j < len(preds) and costs[i][j] < 1.1]
        tp += len(matches)
        fn += len(gt) - len(matches)
        fp += len(preds) - len(matches)
        for i, j in matches:
            g, p = gt[i], preds[j]
            key = g["id"]
            if key in last_ids and last_ids[key] != p["id"]:
                switches += 1
            if key in last_frames and last_frames[key] != index - 1:
                fragments += 1
            last_ids[key], last_frames[key] = p["id"], index
            squared += sum((a - b) ** 2 for a, b in zip(centre(g["box"]), centre(p["box"])))
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(tp / (tp + fp), 6) if tp + fp else None,
        "recall": round(tp / (tp + fn), 6) if tp + fn else None,
        "centre_rmse_normalized": round(math.sqrt(squared / tp), 6) if tp else None,
        "id_switches": switches,
        "fragmentations": fragments,
        "uncertain_predictions_not_counted_as_detections": predictions,
    }


def outputs(entries):
    raw = b"\n".join(encode(e["frame"]) for e in entries) + b"\n"
    a = list(replay(io.BytesIO(raw)))
    b = list(replay(io.BytesIO(raw)))
    assert a == b, "nondeterministic replay"
    baseline = Greedy()
    return a, [baseline.step(e["frame"]) for e in entries]


def recorded(outdir):
    manifest = json.loads((ROOT / "data/aot/manifest.json").read_text())
    entries, records, elapsed = [], [], []
    starts = {}
    previous = None
    registered = 0
    for item in manifest["frames"]:
        data = (ROOT / "data/aot" / item["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        start = time.perf_counter()
        ds = detect_pgm(data)  # Truth is deliberately never an argument to the detector.
        elapsed.append((time.perf_counter() - start) * 1000)
        sequence = item["sequence"]
        if sequence not in starts:
            starts[sequence] = item["time_ns"]
        at = (item["time_ns"] - starts[sequence]) // 1000000
        if sequence == "negative":
            at += 5000
        f = frame(at, ds, kind="rgb")
        f["evidence"] = "recorded"
        f["scene_break"] = (
            not entries or sequence != manifest["frames"][len(entries) - 1]["sequence"]
        )
        f["ego"] = (
            estimate_translation(previous, data)
            if previous is not None and not f["scene_break"]
            else {"dx": 0.0, "dy": 0.0, "variance": 0.05, "valid": False}
        )
        registered += int(f["ego"]["valid"])
        previous = data
        entries.append({"frame": f, "truth": item["truth"]})
        records.append(encode(f))
    actual, baseline = outputs(entries)
    (outdir / "recorded-input.jsonl").write_bytes(b"\n".join(records) + b"\n")
    (outdir / "recorded-output.json").write_text(json.dumps(actual, indent=2) + "\n")
    return {
        "source": "AOT evaluation-only excerpt; fixed-wing aircraft, not UAV",
        "frames": len(entries),
        "temporal": metrics(entries, actual),
        "greedy_iou": metrics(entries, baseline),
        "pixel_detector_latency_ms": {
            "p50": round(statistics.median(elapsed), 3),
            "max": round(max(elapsed), 3),
        },
        "motion": "Translation adapter measured; invalid frames withdraw motion",
        "valid_registration_frames": registered,
        "physical_or_semantic_qualification": False,
    }


def benchmark():
    inputs = []
    for i in range(100):
        ds = [
            detection(0.03 + (j % 8) * 0.12, y=0.1 + (j // 8) * 0.2, w=0.03, h=0.04)
            for j in range(32)
        ]
        inputs.append(encode(frame(i * 100, ds)))
    s = Session()
    timings = []
    cpu_timings = []
    for i, data in enumerate(inputs):
        start = time.perf_counter()
        cpu_start = time.process_time()
        r = s.step(data, now_ms=i * 100)
        timings.append((time.perf_counter() - start) * 1000)
        cpu_timings.append((time.process_time() - cpu_start) * 1000)
        assert len(r["tracks"]) == 32
    s.close()
    tracemalloc.start()
    s = Session()
    for i, data in enumerate(inputs):
        s.step(data, now_ms=i * 100)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    s.close()
    p95 = sorted(timings)[94]
    report = {
        "frames": 100,
        "objects": 32,
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(p95, 3),
        "max_ms": round(max(timings), 3),
        "cpu_p95_ms_diagnostic_only": round(sorted(cpu_timings)[94], 3),
        "peak_bytes": peak,
        "p95_budget_ms": 100,
        "memory_budget_bytes": 32 * 1024 * 1024,
        "passed": p95 <= 100 and peak <= 32 * 1024 * 1024,
    }
    return report


def run(outdir, include_recorded=True):
    outdir.mkdir(parents=True, exist_ok=True)
    reports = {}
    for path in sorted((ROOT / "data/temporal").glob("*.json")):
        entries = json.loads(path.read_text())
        actual, baseline = outputs(entries)
        reports[path.stem] = {
            "temporal": metrics(entries, actual),
            "greedy_iou": metrics(entries, baseline),
        }
        if path.stem in ("fast_uav", "occlusion"):
            assert (
                reports[path.stem]["temporal"]["id_switches"]
                <= reports[path.stem]["greedy_iou"]["id_switches"]
            )
        if path.stem == "clean":
            assert reports[path.stem]["temporal"]["recall"] >= 0.9
    report = {
        "protocol": "matrix-v3.md frozen T09/T10/T13",
        "runtime_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "rescuesense").rglob("*.py")
        },
        "evaluation_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "platform": platform.system() + " " + platform.machine(),
        "synthetic": reports,
        "benchmark": benchmark(),
    }
    if include_recorded:
        report["recorded"] = recorded(outdir)
    (outdir / "temporal-evaluation.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(report, sort_keys=True))
    assert report["benchmark"]["passed"], report["benchmark"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "build/v3")
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    run(args.out, not args.synthetic_only)
