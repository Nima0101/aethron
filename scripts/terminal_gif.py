"""Render captured CLI output as a slowed terminal replay; never a live screenshot."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def run():
    rows = json.loads((ROOT / "docs/assets/demo-output.json").read_text(encoding="utf-8"))
    frames = []
    font = ImageFont.load_default(size=20)
    small = ImageFont.load_default(size=16)
    for index in [15, 18, 19, 21, 3, 5, 11]:
        row = rows[index]
        r = row["result"]
        frame = Image.new("RGB", (1060, 620), "#10212b")
        draw = ImageDraw.Draw(frame)
        draw.text((30, 24), "RescueSense | captured CLI output replay", font=font, fill="#eaf1eb")
        draw.text(
            (30, 60),
            "SYNTHETIC DATA | slowed playback | no live hardware",
            font=small,
            fill="#ffb66e",
        )
        draw.line((30, 96, 1030, 96), fill="#5d7b86")
        draw.text((30, 120), row["scenario"], font=font, fill="#9cdbc3")
        draw.text(
            (30, 158),
            "lighting=" + r["lighting"] + "   version=" + str(r["version"]),
            font=small,
            fill="#aac1c8",
        )
        y = 206
        for c in r["claims"]:
            draw.text(
                (30, y),
                c["capability"] + " / " + c["zone"] + " : " + c["state"],
                font=small,
                fill="#eaf1eb",
            )
            draw.text(
                (45, y + 24),
                "support=" + (",".join(c["sources"]) or "none") + "  confidence=" + c["confidence"],
                font=small,
                fill="#aac1c8",
            )
            y += 56
        draw.text(
            (30, 480),
            "action=" + r["recommendation"]["action"] + " | recommendation only",
            font=font,
            fill="#ffb66e",
        )
        draw.text(
            (30, 527),
            "UNKNOWN never means clearance. No identity or person history.",
            font=small,
            fill="#eaf1eb",
        )
        draw.text(
            (30, 559),
            "Rendered from docs/assets/demo-output.json; not a terminal screenshot.",
            font=small,
            fill="#aac1c8",
        )
        frames.append(frame)
    frames[0].save(
        ROOT / "docs/assets/terminal-replay.gif",
        save_all=True,
        append_images=frames[1:],
        duration=1800,
        loop=0,
    )
    print("Rendered 7 captured CLI result frames; synthetic replay, not live video")


if __name__ == "__main__":
    run()
