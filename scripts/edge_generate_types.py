"""Compatibility entry point for the Node-owned API-v1 client contract generator."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(
            [
                "node",
                str(ROOT / "examples/clients/typescript/generate-contract.mjs"),
                *(sys.argv[1:] or ["--write"]),
            ]
        )
    )
