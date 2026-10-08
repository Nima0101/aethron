"""Capture real CLI output and build an offline replay from those evaluated results."""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def capture():
    from rescuesense.demo import scenarios
    from rescuesense.render import render

    assets = ROOT / "docs/assets"
    assets.mkdir(exist_ok=True)
    start = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "rescuesense", "demo"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    events = []
    rows = []
    for line in process.stdout:
        events.append([round(time.monotonic() - start, 6), "o", line.replace("\n", "\r\n")])
        rows.append(json.loads(line))
    if process.wait() != 0:
        raise SystemExit("demo failed")
    cast = {
        "version": 2,
        "width": 120,
        "height": 32,
        "title": "RescueSense synthetic CLI execution",
        "env": {"TERM": "xterm-256color"},
    }
    (assets / "demo.cast").write_text(
        json.dumps(cast) + "\n" + "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    (assets / "demo-output.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    for name, data in scenarios():
        if name == "person-zero-visible-thermal":
            (ROOT / "examples/person-blackout.json").write_text(
                json.dumps(json.loads(data), indent=2) + "\n", encoding="utf-8"
            )
            (assets / "person-blackout.svg").write_text(render(data, 1000), encoding="utf-8")
        if name == "zero-visible-thermal":
            (ROOT / "examples/thermal-darkness.json").write_text(
                json.dumps(json.loads(data), indent=2) + "\n", encoding="utf-8"
            )
    template = (ROOT / "scripts/replay-template.html").read_text(encoding="utf-8")
    (assets / "replay.html").write_text(
        template.replace("/*RESULTS*/", json.dumps(rows).replace("<", "\\u003c")), encoding="utf-8"
    )
    print("Captured", len(rows), "actual synthetic CLI results; no live hardware evidence")


if __name__ == "__main__":
    capture()
