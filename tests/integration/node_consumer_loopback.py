"""Actual npm/client smoke with a controlled fixture, not the production service."""

import importlib.util
import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def run():
    report = ROOT / "build/p33-sdk-linux/archive-loopback-v3.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)
    spec = importlib.util.spec_from_file_location("smoke", ROOT / "scripts/edge_node_e2e.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    fixture = json.loads((ROOT / "contracts/fixtures/v3/blackout-output.json").read_text())
    scene = {
        "api_version": "1",
        "kind": "scene",
        "sequence": 1,
        "session": "a" * 32,
        "clock": {"domain": "edge_monotonic", "emitted_ms": 0, "valid_for_ms": 100},
        "result": fixture["results"][0],
    }
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def log_message(self, *args):
            pass

        def answer(self, status, body, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            assert self.path == "/api/v1/sessions"
            assert self.headers["Authorization"] == "Bearer " + Service.token
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body == {"source_profile": "bench", "contract": "warn"}
            requests.append("POST")
            self.answer(201, json.dumps({"session": scene["session"], "source_profile": "bench"}).encode())

        def do_GET(self):
            assert self.headers["Authorization"] == "Bearer " + Service.token
            assert self.path == "/api/v1/sessions/" + scene["session"] + "/events"
            requests.append("GET")
            body = "".join(
                "data: " + json.dumps({**scene, "sequence": n}) + "\n\n" for n in range(3)
            )
            self.answer(200, body.encode(), "text/event-stream")

        def do_DELETE(self):
            assert self.headers["Authorization"] == "Bearer " + Service.token
            assert self.path == "/api/v1/sessions/" + scene["session"]
            requests.append("DELETE")
            self.answer(204, b"")

    class Service:
        token = "a" * 64

        @classmethod
        def setUpClass(cls):
            cls.server = HTTPServer(("127.0.0.1", 0), Handler)
            cls.url = "http://127.0.0.1:" + str(cls.server.server_port)
            cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
            try:
                cls.thread.start()
            except BaseException:
                cls.server.server_close()
                raise

        @classmethod
        def tearDownClass(cls):
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=2)
            assert not cls.thread.is_alive()

    module = types.ModuleType("test_edge_http")
    module.HTTPService = Service
    output = ROOT / "build/ecosystem-phase1/node-consumer.json"
    try:
        with patch.dict(sys.modules, {"test_edge_http": module}):
            smoke.run()
        record = json.loads(output.read_text())
        assert requests == ["POST", "GET", "DELETE"], requests
        assert record["display_callbacks"] >= 3 and record["current_state"] == "UNKNOWN"
        record["producer_fixture"] = "Controlled stdlib loopback HTTP; not production aethron_edge service"
        record["requests"] = requests
        report.write_text(json.dumps(record, indent=2) + "\n")
    finally:
        # This fixture must not leave a result that could imply production-service evidence.
        output.unlink(missing_ok=True)
    print("PASS actual build/pack/offline install, loopback POST/GET/DELETE and bound result")


if __name__ == "__main__":
    run()
