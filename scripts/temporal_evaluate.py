"""Frozen tracking metrics, pixel-to-track recorded replay, and resource regression gates."""

import argparse
import hashlib
import io
import json
import math
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aethron.temporal import Session  # noqa: E402 - source-checkout entry point
from aethron.temporal.fixtures import (  # noqa: E402 - source-checkout entry point
    detection,
    encode,
    frame,
)
from aethron.temporal.fusion import observations  # noqa: E402 - source-checkout entry point
from aethron.temporal.math import (  # noqa: E402 - source-checkout entry point
    assignment,
    centre,
    iou,
)
from aethron.temporal.pixels import detect_pgm  # noqa: E402 - source-checkout entry point
from aethron.temporal.registration import estimate_translation  # noqa: E402
from aethron.temporal.replay import replay  # noqa: E402 - source-checkout entry point


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
    # zip silently truncates unequal sequences, hiding missed frames or extra output.
    # Keep this gate explicit under -O and compatible with the Python 3.9 floor.
    if len(entries) != len(results):
        raise ValueError("evaluation_frame_count_mismatch")
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
    if a != b:
        raise AssertionError("nondeterministic replay")
    baseline = Greedy()
    return a, [baseline.step(e["frame"]) for e in entries]


def recorded(outdir):
    payload = (ROOT / "data/aot/manifest.json").read_bytes()
    freeze = json.loads((ROOT / "docs/verification/data-v3-freeze.json").read_bytes())
    if hashlib.sha256(payload).hexdigest() != freeze["files"].get("data/aot/manifest.json"):
        raise ValueError("recorded_manifest_digest")
    manifest = json.loads(payload)
    entries, records, elapsed = [], [], []
    starts = {}
    previous = None
    registered = 0
    for item in manifest["frames"]:
        data = (ROOT / "data/aot" / item["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise AssertionError
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
    if tracemalloc.is_tracing():
        raise ValueError("tracing_already_active")
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
    try:
        for i, data in enumerate(inputs):
            start = time.perf_counter()
            cpu_start = time.process_time()
            r = s.step(data, now_ms=i * 100)
            timings.append((time.perf_counter() - start) * 1000)
            cpu_timings.append((time.process_time() - cpu_start) * 1000)
            if len(r["tracks"]) != 32:
                raise AssertionError
    finally:
        s.close()
    s = None
    tracing_started = False
    try:
        tracemalloc.start()
        tracing_started = True
        # Keep construction inside the original traced measurement scope.
        s = Session()
        for i, data in enumerate(inputs):
            s.step(data, now_ms=i * 100)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        try:
            if tracing_started:
                tracemalloc.stop()
        finally:
            if s is not None:
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


def retain_metric_failure(outdir, fixture, payload, gate, metrics):
    """Preserve this failed attempt without replacing earlier evidence."""
    report = {
        "protocol": "matrix-v3.md frozen T09",
        "passed": False,
        "complete": False,
        "fixture": fixture,
        "fixture_sha256": hashlib.sha256(payload).hexdigest(),
        "evaluation_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "gate": gate,
        "metrics": metrics,
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=outdir,
        prefix="temporal-evaluation-failure-",
        suffix=".json",
        delete=False,
    ) as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + "\n")


def synthetic_fixture_paths():
    """Require the complete synthetic inventory frozen in data-v3-freeze.json."""
    expected = (
        "all_loss.json",
        "blackout.json",
        "camera_pan.json",
        "classes.json",
        "clean.json",
        "crossing.json",
        "fast_uav.json",
        "occlusion.json",
    )
    paths = sorted((ROOT / "data/temporal").glob("*.json"))
    if tuple(path.name for path in paths) != expected or any(not p.is_file() for p in paths):
        raise ValueError("synthetic_fixture_inventory")
    return paths


def synthetic_fixture_payload(path):
    """Bind the bytes consumed below to the repository's trusted freeze manifest."""
    freeze = json.loads((ROOT / "docs/verification/data-v3-freeze.json").read_bytes())
    payload = path.read_bytes()
    name = path.relative_to(ROOT).as_posix()
    if hashlib.sha256(payload).hexdigest() != freeze["files"].get(name):
        raise ValueError("synthetic_fixture_digest")
    return payload


def run(outdir, include_recorded=True):
    outdir.mkdir(parents=True, exist_ok=True)
    reports = {}
    report = {
        "protocol": "matrix-v3.md frozen T09/T10/T13",
        "synthetic": reports,
        "passed": False,
        "failure_stage": "provenance",
    }
    try:
        # Hashing and environment discovery can fail before evaluation starts.
        # Keep them inside the same failure-report boundary as the measurements.
        report["runtime_sha256"] = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "aethron").rglob("*.py")
        }
        report["evaluation_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report["python"] = platform.python_version()
        report["platform"] = platform.system() + " " + platform.machine()
        report["failure_stage"] = "synthetic"
        for path in synthetic_fixture_paths():
            payload = synthetic_fixture_payload(path)
            entries = json.loads(payload.decode("utf-8"))
            actual, baseline = outputs(entries)
            reports[path.stem] = {
                "temporal": metrics(entries, actual),
                "greedy_iou": metrics(entries, baseline),
            }
            if path.stem in ("fast_uav", "occlusion"):
                if not (
                    reports[path.stem]["temporal"]["id_switches"]
                    <= reports[path.stem]["greedy_iou"]["id_switches"]
                ):
                    retain_metric_failure(
                        outdir, path.stem, payload, "id_switches", reports[path.stem]
                    )
                    raise AssertionError
            if path.stem == "clean":
                if not reports[path.stem]["temporal"]["recall"] >= 0.9:
                    retain_metric_failure(
                        outdir, path.stem, payload, "clean_recall", reports[path.stem]
                    )
                    raise AssertionError
        report["failure_stage"] = "benchmark"
        report["benchmark"] = benchmark()
        if include_recorded:
            report["failure_stage"] = "recorded"
            report["recorded"] = recorded(outdir)
        report["failure_stage"] = "benchmark_gate"
        if not report["benchmark"]["passed"]:
            raise AssertionError(report["benchmark"])
        report["passed"] = True
        del report["failure_stage"]
    finally:
        # Keep completed measurements even when a gate or execution is interrupted.
        (outdir / "temporal-evaluation.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n"
        )
    print(json.dumps(report, sort_keys=True))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "build/v3")
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    run(args.out, not args.synthetic_only)
