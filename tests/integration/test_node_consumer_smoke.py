"""Exercise the shipped smoke program with controlled package/server boundaries."""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("node_smoke", ROOT / "scripts/edge_node_e2e.py")
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)
RUN = subprocess.run
EMIT = "for(let n=0;n<3;n++)display({label:'delayed_observation',current_state:'UNKNOWN'});"


class NodeConsumerSmoke(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "build/ecosystem-phase1/node-consumer.json"
        self.archive = self.output.parent / "ts-package/aethron-edge-client-example-0.1.0.tgz"
        self.archive.parent.mkdir(parents=True)
        self.archive.write_bytes(b"controlled archive placeholder; never installed")
        self.output.write_text('{"old_success":true}')
        self.lifecycle = []
        lifecycle = self.lifecycle

        class Service:
            url = "http://127.0.0.1:1"
            token = "synthetic-test-token"

            @classmethod
            def setUpClass(cls):
                lifecycle.append("start")

            @classmethod
            def tearDownClass(cls):
                lifecycle.append("stop")

        self.service = types.ModuleType("test_edge_http")
        self.service.HTTPService = Service

    def invoke(self, body):
        def run(arguments, **kwargs):
            if arguments[0] == "npm":
                self.assertIn("--offline", arguments)
                self.assertIn("--ignore-scripts", arguments)
                package = kwargs["cwd"] / "node_modules/aethron-edge-client-example"
                package.mkdir(parents=True)
                (package / "package.json").write_text(
                    json.dumps({"type": "module", "exports": "./index.js"})
                )
                (package / "index.js").write_text(
                    "export async function observe(base,token,profile,display,signal){" + body + "}"
                )
                return subprocess.CompletedProcess(arguments, 0)
            self.assertEqual(arguments[0], "node")
            return RUN(arguments, **kwargs)

        with (
            patch.object(SMOKE, "ROOT", self.root),
            patch.dict(sys.modules, {"test_edge_http": self.service}),
            patch.object(SMOKE.subprocess, "run", side_effect=run),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            SMOKE.run()

    def test_expected_caller_cancellation_is_success(self):
        try:
            self.invoke(EMIT + "throw new Error('stream_unavailable');")
        except subprocess.CalledProcessError as error:
            self.fail("expected caller cancellation rejected: " + error.stderr)
        record = json.loads(self.output.read_text())
        self.assertEqual(record["display_callbacks"], 3)
        self.assertNotIn("events", record)
        self.assertEqual(record["current_state"], "UNKNOWN")
        self.assertEqual(self.lifecycle, ["start", "stop"])

    def test_display_count_is_not_reported_as_events(self):
        self.invoke(EMIT)
        record = json.loads(self.output.read_text())
        self.assertNotIn("events", record)
        self.assertEqual(record["display_callbacks"], 3)

    def test_non_unknown_display_fails_and_removes_old_success(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(
                "for(let n=0;n<3;n++)display({label:'delayed_observation',current_state:'PRESENT'});"
            )
        self.assertFalse(self.output.exists())
        self.assertEqual(self.lifecycle, ["start", "stop"])

    def test_stream_error_without_own_cancellation_is_not_success(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke("throw new Error('stream_unavailable');")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.lifecycle, ["start", "stop"])

    def test_unrelated_failure_after_cancellation_is_not_success(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(EMIT + "throw new Error('invalid_event');")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.lifecycle, ["start", "stop"])

    def test_legacy_abort_error_is_not_silently_accepted(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(EMIT + "throw new DOMException('unexpected','AbortError');")
        self.assertFalse(self.output.exists())

    def test_no_delayed_displays_is_not_success(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke("display({label:'expired',current_state:'UNKNOWN'});")
        self.assertFalse(self.output.exists())

    def test_missing_archive_removes_old_success(self):
        self.archive.unlink()
        with self.assertRaises(ValueError):
            self.invoke("")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.lifecycle, [])

    def test_current_client_cancellation_matches_smoke(self):
        client = (ROOT / "examples/clients/typescript/dist/client.js").as_uri()
        fixture = json.loads((ROOT / "contracts/fixtures/v3/blackout-output.json").read_text())
        scene = {
            "api_version": "1",
            "kind": "scene",
            "sequence": 1,
            "session": "a" * 32,
            "clock": {"domain": "edge_monotonic", "emitted_ms": 0, "valid_for_ms": 100},
            "result": fixture["results"][0],
        }
        body = "const {observe:realObserve}=await import(" + json.dumps(client) + ");"
        body += "const scene=" + json.dumps(scene) + ";"
        body += r"""
performance.now=()=>0;
globalThis.setInterval=()=>0;
globalThis.clearInterval=()=>{};
let deleted=false;
globalThis.fetch=async(url,options)=>{
 if(options.method==='POST')return Response.json({source_profile:'bench',session:scene.session});
 if(options.method==='DELETE'){deleted=true;return new Response(null,{status:204});}
 const wire=Array.from({length:3},(_,sequence)=>
   'data: '+JSON.stringify({...scene,sequence})+'\n\n').join('');
 return new Response(new ReadableStream({start(controller){
   controller.enqueue(new TextEncoder().encode(wire));
 }}));
};
try {await realObserve(base,token,profile,display,signal);}
finally {if(!deleted)throw new Error('expected_cleanup_missing');}
"""
        self.invoke(body)
        self.assertEqual(json.loads(self.output.read_text())["display_callbacks"], 3)
        self.assertEqual(self.lifecycle, ["start", "stop"])
