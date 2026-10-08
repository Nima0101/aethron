"""Original perception views from actual CLI outputs; inputs explicitly synthetic or licensed recorded."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aethron.temporal.fixtures import detection, encode, frame, sensor  # noqa: E402

COLORS = {
    "person": "#72efab",
    "vehicle": "#68b7ff",
    "uav": "#8ff3fa",
    "hot": "#ffbb5f",
    "obstacle": "#d5bdff",
}
FONT = ImageFont.load_default(size=15)
SMALL = ImageFont.load_default(size=12)
BIG = ImageFont.load_default(size=26)


def inputs():
    rows = []
    for i in range(48):
        camera = -0.002 * i
        person = detection(0.22 + 0.006 * i + camera, y=0.45, w=0.07, h=0.28)
        vehicle = detection(0.60 + camera, y=0.49, w=0.19, h=0.18, kind="vehicle", range_m=12)
        uav = detection(0.55 + 0.004 * i + camera, y=0.16, w=0.025, h=0.025, kind="uav")
        hot = detection(0.77 + camera, y=0.63, w=0.06, h=0.09, kind="hot")
        obstacle = detection(0.36 + camera, y=0.57, w=0.12, h=0.17, kind="obstacle", range_m=5)
        dark = i >= 16
        occluded = 25 <= i <= 28
        f = frame(
            i * 100, [], lighting="zero_visible" if dark else "daylight", dx=-0.002 if i else 0.0
        )
        thermal = [uav, hot] + ([] if occluded else [person])
        f["sensors"] = [
            sensor(i * 100, thermal, "lwir"),
            sensor(i * 100, [vehicle, obstacle], "depth"),
            sensor(i * 100, [dict(person)], "rgb", "dark" if dark else "valid"),
        ]
        if i >= 41:
            for s in f["sensors"]:
                s["quality"] = "dropped"
                s["detections"] = []
        rows.append(
            {
                "frame": f,
                "scene": [person, vehicle, uav, hot, obstacle],
                "occluded": occluded,
                "dark": dark,
                "camera": camera,
            }
        )
    return rows


def sensor_scene(row, thermal=False):
    image = Image.new("RGB", (612, 380))
    draw = ImageDraw.Draw(image)
    dark = row["dark"]
    for y in range(380):
        gray = (
            int(100 + 20 * y / 380) if thermal else (18 + int(y / 25) if dark else 130 + int(y / 5))
        )
        color = (gray, gray, gray) if thermal else ((gray // 2, gray, min(255, gray + 15)))
        draw.line((0, y, 612, y), fill=color)
    horizon = 145
    draw.rectangle(
        (0, horizon, 612, 380), fill=(68, 68, 68) if thermal else ("#151e28" if dark else "#607074")
    )
    shift = int(row["camera"] * 612)
    for x in range(-100, 750, 95):
        xx = x + shift
        draw.rectangle(
            (xx, 90 + (x % 3) * 7, xx + 65, horizon), fill="#686868" if thermal else "#354951"
        )
    draw.polygon(
        [(260 + shift, 145), (375 + shift, 145), (570, 380), (80, 380)],
        fill="#525252" if thermal else "#303c45",
    )
    for yy in range(180, 380, 55):
        draw.line((317 + shift, yy, 317 + shift, yy + 24), fill="#9b9b9b", width=3)
    for d in row["scene"]:
        if d["class"] == "person" and row["occluded"]:
            continue
        x, y, w, h = d["box"]
        x *= 612
        y *= 380
        w *= 612
        h *= 380
        kind = d["class"]
        color = ("#f5f5f5" if kind in ("person", "hot") else "#bcbcbc") if thermal else COLORS[kind]
        if dark and not thermal:
            color = "#263841"
        if kind == "person":
            draw.ellipse((x + w * 0.32, y, x + w * 0.68, y + h * 0.18), fill=color)
            draw.polygon(
                [
                    (x + w * 0.28, y + h * 0.2),
                    (x + w * 0.72, y + h * 0.2),
                    (x + w * 0.85, y + h * 0.58),
                    (x + w * 0.66, y + h * 0.61),
                    (x + w * 0.65, y + h),
                    (x + w * 0.51, y + h),
                    (x + w * 0.48, y + h * 0.64),
                    (x + w * 0.38, y + h),
                    (x + w * 0.2, y + h),
                    (x + w * 0.29, y + h * 0.56),
                    (x + w * 0.1, y + h * 0.5),
                ],
                fill=color,
            )
        elif kind == "vehicle":
            draw.rounded_rectangle((x, y + h * 0.2, x + w, y + h * 0.85), radius=8, fill=color)
            draw.rectangle((x + w * 0.2, y, x + w * 0.8, y + h * 0.45), fill=color)
            for wx in (x + w * 0.2, x + w * 0.8):
                draw.ellipse((wx - 9, y + h * 0.7, wx + 9, y + h), fill="#20262a")
        elif kind == "uav":
            draw.line((x, y, x + w, y + h), fill=color, width=2)
            draw.line((x, y + h, x + w, y), fill=color, width=2)
            draw.ellipse((x + w * 0.3, y + h * 0.3, x + w * 0.7, y + h * 0.7), fill=color)
        else:
            draw.rectangle((x, y, x + w, y + h), fill=color)
    return image


def overlay(image, result, *, sx=1.0, sy=1.0, offset=0):
    draw = ImageDraw.Draw(image)
    for t in result["tracks"]:
        x, y, w, h = t["box"]
        x *= 612 * sx
        y = y * 380 * sy + offset
        w *= 612 * sx
        h *= 380 * sy
        color = COLORS.get(t["class"], "#d5bdff") if t["status"] == "PRESENT" else "#ffc568"
        if t["status"] == "PRESENT":
            draw.rectangle((x, y, x + w, y + h), outline=color, width=2)
        else:
            for xx in range(int(x), int(x + w), 8):
                draw.line((xx, y, min(xx + 4, x + w), y), fill=color, width=2)
                draw.line((xx, y + h, min(xx + 4, x + w), y + h), fill=color, width=2)
            draw.line((x, y, x, y + h), fill=color, width=1)
            draw.line((x + w, y, x + w, y + h), fill=color, width=1)
        label = f"{t['class']} {t['score']:.2f} | {t['state']} {t['freshness_ms']}ms"
        tx = min(max(0, x), max(0, image.width - 270))
        ty = max(offset, y - 18)
        draw.rectangle((tx, ty, tx + 270, ty + 17), fill="#10191f")
        draw.text((tx + 3, ty + 1), label, font=SMALL, fill=color)
    return image


def compose(row, result):
    image = Image.new("RGB", (1280, 660), "#0c151b")
    draw = ImageDraw.Draw(image)
    draw.text((26, 20), "AETHRON / scene-local perception", font=BIG, fill="#e5f3f5")
    draw.text(
        (26, 58),
        "SYNTHETIC SENSOR INPUT  /  ACTUAL CLI TRACKER OUTPUT  /  NO LIVE HARDWARE",
        font=FONT,
        fill="#83a4b4",
    )
    draw.text(
        (26, 96),
        "VISIBLE CAMERA  " + ("ZERO VISIBLE LIGHT / withdrawn" if row["dark"] else "DAYLIGHT"),
        font=FONT,
        fill="#e5f3f5",
    )
    draw.text(
        (652, 96), "LWIR + ACTIVE DEPTH / simulated registered evidence", font=FONT, fill="#e5f3f5"
    )
    left = sensor_scene(row)
    right = overlay(sensor_scene(row, True), result)
    if not row["dark"]:
        left = overlay(left, result)
    image.paste(left, (26, 124))
    image.paste(right, (652, 124))
    draw.text(
        (26, 523),
        f"t={result['at_ms'] / 1000:.1f}s    {result['state']}    recommendation {result['recommendation']['action']}",
        font=BIG,
        fill="#e5f3f5",
    )
    event = (
        "ALL SENSORS LOST: predictions are UNKNOWN, then deleted"
        if result["at_ms"] >= 4100
        else "SHORT OCCLUSION: dashed box is uncertain, not a fresh detection"
        if row["occluded"]
        else "RGB WITHDRAWN: non-visible evidence continues the same temporary track"
        if row["dark"]
        else "CAMERA PAN: compensation separates image shift from object motion"
    )
    draw.text((26, 561), event, font=FONT, fill="#ffc568")
    draw.text(
        (26, 590),
        "Boxes: class + uncalibrated support score + ephemeral track. Prediction horizon 200 ms.",
        font=FONT,
        fill="#a9bdc8",
    )
    draw.text(
        (26, 619),
        "No identity / no cross-scene linkage / no pursuit. Historical replay; snapshots are not live safety outputs.",
        font=SMALL,
        fill="#a9bdc8",
    )
    return image


def run(outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    rows = inputs()
    with tempfile.TemporaryDirectory(prefix="aethron-visual-") as temp:
        file = Path(temp) / "input.jsonl"
        file.write_bytes(b"\n".join(encode(r["frame"]) for r in rows) + b"\n")
        process = subprocess.run(
            [sys.executable, "-m", "aethron", "replay", str(file)],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
    results = [json.loads(line) for line in process.stdout.splitlines()]
    assert len(results) == 48 and results[-1]["state"] == "UNKNOWN" and not results[-1]["tracks"]
    assert "rgb" not in results[20]["tracks"][0]["sources"]
    (outdir / "perception-output.json").write_bytes(process.stdout)
    (outdir / "perception-input.jsonl").write_bytes(
        b"\n".join(encode(r["frame"]) for r in rows) + b"\n"
    )
    frames = [compose(row, result) for row, result in zip(rows, results)]
    frames[8].save(outdir / "perception-day.png")
    frames[23].save(outdir / "perception-night.png")
    frames[26].save(outdir / "perception-occlusion.png")
    frames[43].save(outdir / "perception-unknown.png")
    frames[0].save(
        outdir / "perception.gif",
        save_all=True,
        append_images=frames[1:],
        duration=150,
        loop=0,
        optimize=False,
        disposal=2,
    )
    (outdir / "perception.html").write_text(
        """<!doctype html><meta charset="utf-8"><title>AETHRON recorded synthetic execution</title><style>body{background:#0c151b;color:#e5f3f5;font:18px system-ui;max-width:1280px;margin:32px auto}img{max-width:100%}a{color:#8ff3fa}</style><h1>Scene-local perception</h1><p>Original synthetic scene; overlays from actual AETHRON CLI. Playback is slowed to 150 ms per 100 ms input frame. No live sensor claim.</p><img src="perception.gif" alt="Daylight to zero-visible-light, short occlusion, then all-sensor loss"><p><a href="perception-output.json">Actual outputs</a> · <a href="perception-input.jsonl">Reproduce the inputs</a></p>"""
    )
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(outdir.glob("perception*"))
        if p.is_file() and p.name != "perception-manifest.json"
    }
    (outdir / "perception-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "frames": len(frames),
                "actual_cli": True,
                "synthetic_inputs": True,
                "sha256": manifest,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "docs/assets")
    run(parser.parse_args().out)
