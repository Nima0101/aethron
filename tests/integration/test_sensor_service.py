"""Real signed appliance CLI, offline sensor worker and authenticated external clients."""

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from test_sensor_appliance import fixture

import aethron


class SensorService(unittest.TestCase):
    def test_signed_appliance_processes_without_viewer_and_exports_only_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            bundle.mkdir()
            config_path, _, _, _ = fixture(bundle)
            private, public = root / "test-only.pem", root / "test-only.pub"
            for args in (
                ["genpkey", "-algorithm", "ED25519", "-out", str(private)],
                ["pkey", "-in", str(private), "-pubout", "-out", str(public)],
            ):
                subprocess.run(["openssl", *args], check=True, capture_output=True)
            token = root / "token"
            token.write_text("a" * 64)
            token.chmod(0o600)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config = json.loads(config_path.read_text())
            config.update(
                port=port,
                status_file=str(root / "status.json"),
                integrity_bundle=".",
                trust_root=str(public),
                credentials=[
                    {
                        "token_file": str(token),
                        "principal": {"name": "test", "scopes": ["observe", "session:manage"]},
                    }
                ],
            )
            config_path.write_text(json.dumps(config))
            manifest = {
                "schema_version": 1,
                "version": 1,
                "config_version": 1,
                "files": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()
                },
            }
            (bundle / "manifest.json").write_text(json.dumps(manifest))
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-rawin",
                    "-inkey",
                    str(private),
                    "-in",
                    str(bundle / "manifest.json"),
                    "-out",
                    str(bundle / "manifest.sig"),
                ],
                check=True,
                capture_output=True,
            )
            env = dict(os.environ)
            if env.get("PYTHONPATH"):
                env["PYTHONPATH"] = os.pathsep.join(
                    str(Path(p).resolve())
                    for p in [
                        *env["PYTHONPATH"].split(os.pathsep),
                        str(Path(aethron.__file__).resolve().parent.parent),
                    ]
                )
            with (root / "server.log").open("w+") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "aethron_edge", "run", "--config", str(config_path)],
                    cwd=root,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                url = f"http://127.0.0.1:{port}"
                try:
                    deadline = time.monotonic() + 15
                    state = None
                    while time.monotonic() < deadline:
                        if (root / "status.json").exists():
                            state = json.loads((root / "status.json").read_text())
                            if state["sensors"]["depth"]["batches"] >= 3:
                                break
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(log.read())
                        time.sleep(0.05)
                    if state is None:
                        log.seek(0)
                        self.fail(
                            f"no status before startup deadline; exit={process.poll()}; {log.read()}"
                        )
                    self.assertGreaterEqual(state["sensors"]["depth"]["batches"], 3)
                    self.assertEqual(state["inferences"], 0)

                    def request(route, *, data=None, method=None, authenticated=True):
                        headers = {"Authorization": "Bearer " + "a" * 64} if authenticated else {}
                        if data is not None:
                            headers["Content-Type"] = "application/json"
                            data = json.dumps(data).encode()
                        return urllib.request.urlopen(
                            urllib.request.Request(
                                url + route, data=data, method=method, headers=headers
                            ),
                            timeout=5,
                        )

                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request("/api/v1/capabilities", authenticated=False)
                    self.assertEqual(error.exception.code, 401)
                    with request("/api/v1/capabilities") as response:
                        capabilities = json.load(response)
                    self.assertEqual(capabilities["drivers"], ["sensor-replay"])
                    self.assertEqual(capabilities["provider"], "recorded_geometry")
                    with request(
                        "/api/v1/sessions", data={"source_profile": "depth", "contract": "warn"}
                    ) as response:
                        handle = json.load(response)["session"]
                    with request(f"/api/v1/sessions/{handle}/events") as response:
                        self.assertEqual(response.readline(), b"event: gap\n")
                        gap = json.loads(response.readline().removeprefix(b"data: "))
                        self.assertEqual(gap["scene_state"], "UNKNOWN")
                        self.assertEqual(response.readline(), b"\n")
                        for _ in range(3):
                            self.assertEqual(response.readline(), b"event: scene\n")
                            scene = json.loads(response.readline().removeprefix(b"data: "))
                            self.assertEqual(scene["result"]["state"], "UNKNOWN")
                            self.assertEqual(scene["result"]["tracks"], [])
                            self.assertEqual(scene["clock"]["valid_for_ms"], 0)
                            self.assertNotIn("camera_xyz", json.dumps(scene))
                            self.assertEqual(response.readline(), b"\n")
                    with request(f"/api/v1/sessions/{handle}", method="DELETE") as response:
                        self.assertEqual(response.status, 204)
                    before = json.loads((root / "status.json").read_text())["sensors"]["depth"][
                        "batches"
                    ]
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        after = json.loads((root / "status.json").read_text())["sensors"]["depth"][
                            "batches"
                        ]
                        if after > before:
                            break
                        time.sleep(0.05)
                    self.assertGreater(after, before)
                finally:
                    process.terminate()
                    process.wait(timeout=10)
