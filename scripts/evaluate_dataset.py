"""Reproducible synthetic software evaluation, not perception accuracy."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hashlib
import json
import random

from aethron import evaluate
from aethron.demo import scenarios


def corpus():
    base = json.loads(next(iter(scenarios()))[1])
    rng = random.Random(78123)
    for i in range(240):
        truth = (i // 4) % 2 == 0
        score = 0.95 if truth else 0.05
        if i % 10 == 0:
            score = 0.05 if truth else 0.95
        if i % 13 == 0:
            score = rng.uniform(0.3, 0.7)
        doc = dict(
            base,
            version=2,
            mode="direct",
            lighting=["daylight", "low_light", "near_dark", "zero_visible"][i % 4],
        )
        obs = dict(base["observations"][0], values=[score], rect=[20, 20, 30, 50])
        doc["observations"] = [
            obs,
            dict(obs, sensor="thermal_person", quality="dropped" if i % 17 == 0 else "valid"),
        ]
        yield {"case": i, "domain": "person", "truth": truth, "input": doc}
    for i in range(80):
        truth = i % 2 == 0
        temperature = 180 if truth or i % 4 == 1 else 25
        doc = dict(base, observations=[dict(base["observations"][1], values=[temperature])])
        yield {"case": 240 + i, "domain": "fire_like", "truth": truth, "input": doc}


def report():
    rows = list(corpus())
    groups = {}
    for row in rows:
        out = evaluate(json.dumps(row["input"]).encode())
        cap = "human_presence" if row["domain"] == "person" else "thermal_source"
        c = next(c for c in out["claims"] if c["capability"] == cap)
        key = row["domain"] + "/" + out["lighting"]
        bucket = groups.setdefault(
            key,
            {"TP": 0, "FP": 0, "TN": 0, "FN": 0, "UNKNOWN": 0, "positive_unknown": 0, "total": 0},
        )
        bucket["total"] += 1
        if c["state"] == "UNKNOWN":
            bucket["UNKNOWN"] += 1
            bucket["positive_unknown"] += int(row["truth"])
        else:
            positive = c["state"] == "PRESENT" and (
                row["domain"] == "person" or c["kind"] == "fire_like"
            )
            bucket[("T" if positive == row["truth"] else "F") + ("P" if positive else "N")] += 1
    data = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
    return data, {
        "evidence": "synthetic_only",
        "training": "none",
        "cases": len(rows),
        "sha256": hashlib.sha256(data).hexdigest(),
        "groups": groups,
        "limitation": "Synthetic cue software test, not detector accuracy. UNKNOWN positive cases are missed cues. Fire-like is not fire diagnosis.",
    }


if __name__ == "__main__":
    data, result = report()
    if "--write" in sys.argv:
        Path("examples/evaluation.jsonl").write_bytes(data)
    else:
        assert Path("examples/evaluation.jsonl").read_bytes() == data, (
            "corpus differs from generator"
        )
    print(json.dumps(result, indent=2, sort_keys=True))
