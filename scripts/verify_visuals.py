"""Verify README images/input/output reproduce exactly using pinned Pillow."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
produced = Path(sys.argv[1])
for name in (
    "perception-day.png",
    "perception-night.png",
    "perception-occlusion.png",
    "perception-unknown.png",
    "perception.gif",
    "perception-input.jsonl",
    "perception-output.json",
    "perception.html",
    "perception-manifest.json",
):
    assert (produced / name).read_bytes() == (ROOT / "docs/assets" / name).read_bytes(), name
print("PASS: actual README perception artifacts reproduced byte for byte")
