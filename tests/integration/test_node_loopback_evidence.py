"""Controlled fixture checks: no npm, sockets, production service or device run."""

import contextlib
import inspect
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/integration/node_consumer_loopback.py"


class LoopbackEvidence(unittest.TestCase):
    def invoke(self, case, optimize):
        namespace = {"__name__": "loopback_fixture_test", "__file__": str(SOURCE)}
        exec(compile(SOURCE.read_text(), str(SOURCE), "exec", optimize=optimize), namespace)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            namespace["ROOT"] = root
            fixture = root / "contracts/fixtures/v3/blackout-output.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text('{"results":[{}]}')
            output = root / "build/ecosystem-phase1/node-consumer.json"
            output.parent.mkdir(parents=True)
            report = root / "build/p33-sdk-linux/archive-loopback-v3.json"
            report.parent.mkdir(parents=True)
            report.write_text('{"old_success":true}')

            def smoke_run():
                service = namespace["sys"].modules["test_edge_http"].HTTPService
                handler_class = inspect.getclosurevars(
                    service.setUpClass.__func__
                ).nonlocals["Handler"]
                methods = [] if case == "missing_requests" else ["POST", "GET", "DELETE"]
                if case == "wrong_order":
                    methods.reverse()
                for method in methods:
                    handler = object.__new__(handler_class)
                    handler.path = "/api/v1/sessions"
                    if method != "POST":
                        handler.path += "/" + "a" * 32
                    if method == "GET":
                        handler.path += "/events"
                    body = json.dumps(
                        {"source_profile": "bench", "contract": "warn"}
                    ).encode()
                    if case == "wrong_body" and method == "POST":
                        body = b'{}'
                    handler.headers = {
                        "Authorization": "Bearer " + service.token,
                        "Content-Length": str(len(body)),
                    }
                    if case == method + "_path":
                        handler.path = "/wrong"
                    if case == method + "_authorization":
                        handler.headers["Authorization"] = "Bearer wrong"
                    handler.rfile = io.BytesIO(body)
                    handler.wfile = io.BytesIO()
                    handler.send_response = lambda *args: None
                    handler.send_header = lambda *args: None
                    handler.end_headers = lambda: None
                    getattr(handler, "do_" + method)()
                record = {
                    "display_callbacks": 3,
                    "current_state": "UNKNOWN",
                    "installed_client": True,
                }
                if case == "wrong_state":
                    record["current_state"] = "PRESENT"
                if case == "float_count":
                    record["display_callbacks"] = 3.5
                if case == "boolean_count":
                    record["display_callbacks"] = True
                if case == "not_installed":
                    record["installed_client"] = False
                if case == "live_thread":
                    service.server = types.SimpleNamespace(
                        shutdown=lambda: None, server_close=lambda: None
                    )
                    service.thread = types.SimpleNamespace(
                        join=lambda timeout: None, is_alive=lambda: True
                    )
                    service.tearDownClass()
                output.write_text(json.dumps(record))

            module = types.SimpleNamespace(run=smoke_run)
            spec = types.SimpleNamespace(
                loader=types.SimpleNamespace(exec_module=lambda value: None)
            )
            error = None
            with (
                patch.object(
                    namespace["importlib"].util, "spec_from_file_location", return_value=spec
                ),
                patch.object(
                    namespace["importlib"].util, "module_from_spec", return_value=module
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                try:
                    namespace["run"]()
                except (AssertionError, ValueError, TypeError) as caught:
                    error = caught
            self.assertFalse(
                output.exists(), "temporary service-style evidence must always be removed"
            )
            if case == "valid":
                self.assertIsNone(error)
                result = json.loads(report.read_text())
                self.assertEqual(result["requests"], ["POST", "GET", "DELETE"])
                self.assertIn("not production", result["producer_fixture"])
            else:
                self.assertIsInstance(error, ValueError, case)
                self.assertEqual(str(error), "invalid_loopback_evidence")
                self.assertFalse(report.exists(), case)

    def test_valid_control(self):
        for optimize in [0, 2]:
            with self.subTest(optimize=optimize):
                self.invoke("valid", optimize)

    def test_reject_contradictory_evidence(self):
        cases = [
            "missing_requests", "wrong_order", "wrong_body", "wrong_state",
            "float_count", "boolean_count", "not_installed", "live_thread",
        ]
        cases += [
            method + suffix
            for method in ["POST", "GET", "DELETE"]
            for suffix in ["_path", "_authorization"]
        ]
        for optimize in [0, 2]:
            for case in cases:
                with self.subTest(optimize=optimize, case=case):
                    self.invoke(case, optimize)
