"""Linux container check of actual selected-slot exec before the full boot soak."""

import json
import os
import subprocess
import time
from pathlib import Path


def run():
    subprocess.run(
        ["/opt/aethron/venv/bin/python", "-B", "/opt/aethron-sil/update_probe.py"], check=True
    )
    # The service UID must not be able to rename the protected update store,
    # replace active.json or lower its minimum-version record.
    forbidden = "from pathlib import Path; Path('/var/lib/aethron-updates').rename('/var/lib/aethron/hijack')"
    denied = subprocess.run(
        ["/opt/aethron/venv/bin/python", "-c", forbidden],
        user="aethron",
        group="aethron",
        capture_output=True,
        check=False,
    )
    assert denied.returncode != 0 and b"PermissionError" in denied.stderr
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    server = subprocess.Popen(
        [
            "/opt/aethron/venv/bin/python",
            "-I",
            "-m",
            "aethron_edge",
            "run",
            "--config",
            "/opt/aethron/appliance.json",
            "--update-store",
            "/var/lib/aethron-updates",
        ],
        user="aethron",
        group="aethron",
        env=env,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise AssertionError("selected runtime failed startup")
            try:
                status = json.loads(Path("/var/lib/aethron/status.json").read_text())
                args = Path(f"/proc/{server.pid}/cmdline").read_bytes()
                if b"/aethron-updates/2-" in args and status["processed"] > 3:
                    print(
                        json.dumps(
                            {
                                "selected_runtime_exec": True,
                                "version": 2,
                                "offline_processing": True,
                                "service_cannot_replace_update_store": True,
                                "hardware_qualified": False,
                            }
                        )
                    )
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.1)
        raise AssertionError("selected runtime did not process")
    finally:
        server.terminate()
        server.wait(timeout=15)


if __name__ == "__main__":
    run()
