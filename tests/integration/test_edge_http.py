"""Real subprocess server and network clients, never an in-process test client."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


class HTTPService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.token = "a" * 64
        other = "b" * 64
        creds = []
        for name, token in [("owner", cls.token), ("other", other)]:
            path = cls.directory / name
            path.write_text(token)
            path.chmod(0o600)
            creds.append(
                {
                    "token_file": str(path),
                    "principal": {"name": name, "scopes": ["observe", "session:manage"]},
                }
            )
        cls.status = cls.directory / "status.json"
        config = {
            "version": 1,
            "runtime_mode": "interactive",
            "port": cls.port,
            "profiles": [
                {
                    "name": "bench",
                    "driver": "replay",
                    "address": str(ROOT / "examples/temporal-blackout.jsonl"),
                }
            ],
            "credentials": creds,
            "status_file": str(cls.status),
        }
        path = cls.directory / "appliance.json"
        path.write_text(json.dumps(config))
        env = dict(os.environ, PYTHONPATH=str(ROOT / "integrations/edge") + os.pathsep + str(ROOT))
        cls.log = (cls.directory / "server.log").open("w+")
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "aethron_edge", "run", "--config", str(path)],
            cwd=cls.directory,
            env=env,
            stdout=cls.log,
            stderr=cls.log,
        )
        cls.url = f"http://127.0.0.1:{cls.port}"
        cls.client = httpx.Client(
            base_url=cls.url, headers={"Authorization": "Bearer " + cls.token}, timeout=5
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if cls.client.get("/healthz").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if cls.process.poll() is not None:
                break
            time.sleep(0.05)
        cls.log.seek(0)
        reason = cls.log.read()
        cls.tearDownClass()
        raise AssertionError("server not ready: " + reason)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        if cls.process.poll() is None:
            cls.process.terminate()
            cls.process.wait(timeout=10)
        cls.log.close()
        cls.temp.cleanup()

    def test_auth_origin_host_and_no_source_injection(self):
        for headers, expected in [
            ({"Authorization": "Bearer wrong"}, 401),
            ({"Origin": "https://evil.invalid"}, 403),
            ({"Host": "evil.invalid"}, 403),
        ]:
            self.assertEqual(
                self.client.get("/api/v1/capabilities", headers=headers).status_code, expected
            )
        r = self.client.post(
            "/api/v1/sessions",
            json={"source_profile": "rtsp://private-sentinel", "contract": "warn"},
        )
        self.assertEqual(r.status_code, 422)
        self.assertNotIn("private-sentinel", r.text)
        self.assertEqual(self.client.post("/api/v1/frames", json={}).status_code, 404)

    def test_session_ownership_capacity_and_detach_independence(self):
        handles = []
        try:
            for _ in range(4):
                r = self.client.post(
                    "/api/v1/sessions", json={"source_profile": "bench", "contract": "warn"}
                )
                self.assertEqual(r.status_code, 201)
                handles.append(r.json()["session"])
            self.assertEqual(
                self.client.post(
                    "/api/v1/sessions", json={"source_profile": "bench", "contract": "warn"}
                ).status_code,
                429,
            )
            route = f"/api/v1/sessions/{handles[0]}/snapshot"
            self.assertEqual(
                self.client.get(route, headers={"Authorization": "Bearer " + "b" * 64}).status_code,
                403,
            )
            r = self.client.get(route)
            self.assertEqual(r.status_code, 200)
            self.assertLessEqual(r.json()["clock"]["valid_for_ms"], 100)
        finally:
            for handle in handles:
                self.client.delete("/api/v1/sessions/" + handle)
        time.sleep(1.1)
        before = json.loads(self.status.read_text())["processed"]
        time.sleep(1.1)
        after = json.loads(self.status.read_text())["processed"]
        self.assertGreater(after, before)

    def test_raw_replay_validation_and_limit(self):
        r = self.client.post(
            "/api/v1/replays",
            content=(ROOT / "examples/temporal-blackout.jsonl").read_bytes(),
            headers={"Content-Type": "application/x-ndjson"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["frame_count"], 24)
        self.assertEqual(self.client.post("/api/v1/replays", content=b" " * 65537).status_code, 413)
        r = self.client.post("/api/v1/replays", content=b'{"private":"private-sentinel"}')
        self.assertEqual(r.status_code, 422)
        self.assertNotIn("private-sentinel", r.text)

    def test_sse_reconnect_starts_with_gap_not_history(self):
        handle = self.client.post(
            "/api/v1/sessions", json={"source_profile": "bench", "contract": "warn"}
        ).json()["session"]
        try:
            with self.client.stream(
                "GET",
                f"/api/v1/sessions/{handle}/events",
                headers={"Last-Event-ID": "old-private-id"},
            ) as stream:
                lines = stream.iter_lines()
                self.assertEqual(next(lines), "event: gap")
                self.assertNotIn("old-private-id", next(lines))
                next(lines)
                self.assertEqual(next(lines), "event: scene")
        finally:
            self.client.delete("/api/v1/sessions/" + handle)
