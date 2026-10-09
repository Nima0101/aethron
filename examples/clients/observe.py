"""Run from anywhere after installing AETHRON edge and HTTPX."""

import argparse
import json
from pathlib import Path

from aethron_edge.client import observe

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8765")
parser.add_argument("--token-file", required=True, type=Path)
parser.add_argument("--profile", required=True)
parser.add_argument("--contract", default="warn")
parser.add_argument("--limit", type=int)
args = parser.parse_args()
try:
    for event in observe(
        args.url, args.token_file.read_text().strip(), args.profile, args.contract, args.limit
    ):
        print(json.dumps(event), flush=True)
except (ValueError, OSError):
    print('{"current_state":"UNKNOWN","label":"disconnected"}')
    raise SystemExit(1) from None
