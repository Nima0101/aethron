"""Local tooling; explicit operations only, fixed errors without input echo."""

import argparse
import importlib.metadata
import json
from pathlib import Path

from . import __version__
from .protocol import replay_bytes


def main():
    parser = argparse.ArgumentParser(prog="aethron-edge")
    parser.add_argument("command", choices=["doctor", "replay", "export-openapi"])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "export-openapi":
        from .openapi import document

        if args.out is None:
            parser.error("--out required")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(document(), sort_keys=True, indent=2) + "\n")
        return
    if args.config is None:
        parser.error("--config required")
    try:
        config = json.loads(args.config.read_text())
        if config.get("version") != 1:
            raise ValueError("invalid_request")
        if args.command == "doctor":
            result = {
                "edge_version": __version__,
                "core_version": importlib.metadata.version("aethron"),
                "hardware_probed": False,
                "qualified": False,
                "model": "not_loaded",
                "provider": "not_selected",
            }
        else:
            path = (args.config.parent / config["replay"]).resolve()
            with path.open("rb") as stream:
                data = stream.read(20 * 1024 * 1024 + 1)
            result = replay_bytes(data).model_dump(by_alias=True)
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    except (ValueError, OSError, KeyError):
        parser.exit(2, "invalid_request\n")
