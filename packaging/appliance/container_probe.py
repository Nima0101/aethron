"""Run only inside the candidate container: installed server/client without WAN."""

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
from aethron_edge.client import observe


def run():
    root = Path("/work")
    token = root / "token"
    token.write_text("e" * 64)
    token.chmod(0o600)
    config = {
        "version": 1,
        "runtime_mode": "interactive",
        "status_file": "/work/status.json",
        "profiles": [{"name": "fixture", "driver": "replay", "address": "/fixture.jsonl"}],
        "credentials": [
            {
                "token_file": str(token),
                "principal": {"name": "consumer", "scopes": ["observe", "session:manage"]},
            }
        ],
    }
    (root / "config.json").write_text(json.dumps(config))
    server = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-m",
            "aethron_edge",
            "serve",
            "--config",
            str(root / "config.json"),
        ],
        stdout=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url="http://127.0.0.1:8765", timeout=1) as client:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    if client.get("/healthz").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
        events = list(observe("http://127.0.0.1:8765", token.read_text(), "fixture", limit=3))
        assert len(events) == 3 and all(e["current_state"] == "UNKNOWN" for e in events)
        before = json.loads((root / "status.json").read_text())["processed"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            after = json.loads((root / "status.json").read_text())["processed"]
            if after > before:
                break
            time.sleep(0.1)
        assert after > before
        print(
            json.dumps(
                {
                    "installed_http_sse": True,
                    "events": len(events),
                    "offline": True,
                    "zero_viewer_processing": True,
                    "hardware_qualified": False,
                }
            )
        )
    finally:
        server.terminate()
        server.wait(timeout=15)


if __name__ == "__main__":
    run()
