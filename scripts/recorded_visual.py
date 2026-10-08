"""Render the retained recorded-data failure, with attribution and no invented detections."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def run():
    outputs = json.loads((ROOT / "build/v3-registered/recorded-output.json").read_text())
    frames = []
    for i, result in enumerate(outputs):
        image = Image.new("RGB", (1000, 680), "#0c151b")
        draw = ImageDraw.Draw(image)
        draw.text(
            (24, 18),
            "RECORDED CAMERA / baseline failure retained",
            font=ImageFont.load_default(size=25),
            fill="#e4f0f4",
        )
        view = Image.open(ROOT / "data/aot" / f"{i:03}.pgm").convert("RGB")
        pen = ImageDraw.Draw(view)
        for t in result["tracks"]:
            x, y, w, h = t["box"]
            x *= 612
            y *= 512
            w *= 612
            h *= 512
            pen.rectangle((x, y, x + w, y + h), outline="#ffbb5f", width=1)
        image.paste(view, (24, 75))
        lines = [
            "ACTUAL PIXELS -> DETECTOR",
            "-> REGISTRATION -> TRACKER",
            "",
            f"Frame {i + 1}/25",
            f"Output: {result['state']}",
            f"Proposals retained: {len(result['tracks'])}",
            "",
            "Tiny aircraft were missed.",
            "Background false positives remain.",
            "",
            "No UAV or thermal qualification.",
            "No live hardware claim.",
        ]
        for j, line in enumerate(lines):
            draw.text(
                (656, 90 + j * 28),
                line,
                font=ImageFont.load_default(size=15),
                fill="#ffcb88" if j in (8, 9) else "#c0d6df",
            )
        draw.text(
            (24, 614),
            "Amazon Airborne Object Tracking / CDLA-Permissive-1.0 / resized excerpt; AETHRON overlays",
            font=ImageFont.load_default(size=15),
            fill="#c0d6df",
        )
        draw.text(
            (24, 644),
            "Full error counts and source hashes are published. This capture is not a successful detection demo.",
            font=ImageFont.load_default(size=15),
            fill="#c0d6df",
        )
        frames.append(image)
    out = ROOT / "docs/assets"
    frames[0].save(out / "recorded-failure.png")
    frames[0].save(
        out / "recorded-failure.gif",
        save_all=True,
        append_images=frames[1:],
        duration=150,
        loop=0,
        optimize=False,
    )
    print("Rendered actual25-frame recorded evaluation, with failure and data attribution visible")


if __name__ == "__main__":
    run()
