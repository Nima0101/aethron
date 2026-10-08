"""Actual model detections over licensed still photographs; no inferred identity."""

import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rescuesense.temporal.fixtures import encode, frame  # noqa: E402
from rescuesense.temporal.replay import replay  # noqa: E402
from rescuesense.vision.yolox import RGBDetector  # noqa: E402


def run():
    model = RGBDetector(ROOT / "build/models/yolox.onnx")
    out = ROOT / "build/vision"
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    panels = []
    for name in ("person", "animal"):
        image = Image.open(ROOT / "data/rgb-smoke" / f"{name}.png").convert("RGB")
        ds = model.infer(np.array(image), lighting="daylight")
        f = frame(0, ds, kind="rgb")
        f["evidence"] = "recorded"
        result = list(replay(io.BytesIO(encode(f))))[0]
        report[name] = {
            "expected_class_present": any(d["class"] == name for d in ds),
            "result": result,
        }
        panel = Image.new("RGB", (550, 670), "#0c151b")
        shown = image.copy()
        shown.thumbnail((512, 512))
        panel.paste(shown, (19, 90))
        draw = ImageDraw.Draw(panel)
        font = ImageFont.load_default(size=16)
        draw.text((19, 20), "ACTUAL RGB MODEL OUTPUT / licensed still", font=font, fill="#d7ecee")
        for t in result["tracks"]:
            x, y, w, h = t["box"]
            x = x * shown.width + 19
            y = y * shown.height + 90
            w *= shown.width
            h *= shown.height
            draw.rectangle((x, y, x + w, y + h), outline="#72efab", width=3)
            label = f"{t['class']} {t['score']:.3f} / {t['state']} / {t['freshness_ms']}ms"
            draw.rectangle((19, 54, 530, 80), fill="#193d32")
            draw.text((24, 58), label, font=font, fill="#aaf4c4")
        draw.text(
            (19, 615),
            "NASA public domain" if name == "person" else "Photo: Stefan van der Walt / CC0",
            font=font,
            fill="#b5cbd4",
        )
        draw.text(
            (19, 642),
            "Smoke test only. No field accuracy or identity claim.",
            font=ImageFont.load_default(size=13),
            fill="#b5cbd4",
        )
        panels.append(panel)
    combined = Image.new("RGB", (1100, 670))
    combined.paste(panels[0])
    combined.paste(panels[1], (550, 0))
    combined.save(ROOT / "docs/assets/rgb-model-execution.png")
    (out / "smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    assert all(v["expected_class_present"] for v in report.values()), "retain model smoke failure"


if __name__ == "__main__":
    run()
