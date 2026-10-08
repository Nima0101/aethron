"""One bounded input per process; no persistent observations or network."""

import argparse
import json
import sys
from pathlib import Path

from .core import evaluate
from .schema import MAX_BYTES


def main():
    parser = argparse.ArgumentParser(
        description="AETHRON reference runtime; no live hardware claim"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="run explicitly synthetic safety scenarios")
    rp = sub.add_parser("replay", help="bounded recorded/synthetic temporal JSONL")
    rp.add_argument("file")
    for name in ("evaluate", "render"):
        p = sub.add_parser(name)
        p.add_argument("file", help="bounded protocol JSON file or - for stdin")
        if name == "render":
            p.add_argument("--now-ms", required=True, type=int)
    args = parser.parse_args()
    try:
        if args.command == "demo":
            from .demo import run

            run()
            return 0
        if args.command == "replay":
            from .temporal.replay import ReplayError, replay

            try:
                with Path(args.file).open("rb") as stream:
                    for result in replay(stream):
                        print(json.dumps(result, sort_keys=True))
            except ReplayError as exc:
                print(
                    json.dumps(
                        {"error": "invalid_input_or_io", "action": exc.action, "state": "UNKNOWN"}
                    ),
                    file=sys.stderr,
                )
                return 2
            return 0
        if args.file == "-":
            data = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            with Path(args.file).open("rb") as stream:
                data = stream.read(MAX_BYTES + 1)
        if args.command == "evaluate":
            print(json.dumps(evaluate(data), sort_keys=True))
        else:
            from .render import render

            sys.stdout.buffer.write((render(data, args.now_ms) + "\n").encode("utf-8"))
        return 0
    except (ValueError, OSError):
        print('{"error":"invalid_input_or_io","action":"WARN","state":"UNKNOWN"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
