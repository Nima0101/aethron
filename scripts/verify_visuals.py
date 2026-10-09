"""Verify README artifacts byte-for-byte; diagnose drift without relaxing the gate."""

import argparse
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    "perception-day.png",
    "perception-night.png",
    "perception-occlusion.png",
    "perception-unknown.png",
    "perception.gif",
    "perception-input.jsonl",
    "perception-output.json",
    "perception.html",
    "perception-manifest.json",
)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _png_diagnostic(expected, actual):
    try:
        from PIL import Image, __version__, features

        with Image.open(io.BytesIO(expected)) as left, Image.open(io.BytesIO(actual)) as right:
            left_pixels = left.convert("RGBA").tobytes()
            right_pixels = right.convert("RGBA").tobytes()
            return {
                "reason": "png_encoding"
                if left.size == right.size and left_pixels == right_pixels
                else "png_pixels",
                "expected_pixels_sha256": _digest(left_pixels),
                "actual_pixels_sha256": _digest(right_pixels),
                "expected_size": list(left.size),
                "actual_size": list(right.size),
                "pillow": __version__,
                "zlib": features.version_codec("zlib"),
            }
    except (ImportError, OSError, ValueError):
        return {"reason": "png_diagnostic_unavailable"}


def verify(produced, reference):
    differences = []
    for name in ARTIFACTS:
        try:
            expected = (reference / name).read_bytes()
            actual = (produced / name).read_bytes()
        except OSError:
            differences.append({"file": name, "reason": "missing_or_unreadable"})
            continue
        if expected == actual:
            continue
        row = {
            "file": name,
            "reason": "bytes",
            "expected_sha256": _digest(expected),
            "actual_sha256": _digest(actual),
        }
        if name.endswith(".png"):
            row.update(_png_diagnostic(expected, actual))
        differences.append(row)
    return {"byte_identical": not differences, "differences": differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("produced", type=Path)
    parser.add_argument("--reference", type=Path, default=ROOT / "docs/assets")
    args = parser.parse_args()
    report = verify(args.produced, args.reference)
    if not report["byte_identical"]:
        print(json.dumps(report, sort_keys=True))
        return 1
    print("PASS: actual README perception artifacts reproduced byte for byte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
