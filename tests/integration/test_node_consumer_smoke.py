"""Exercise the shipped smoke program with controlled package/server boundaries."""

import contextlib
import hashlib
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
        self.package = self.root / "examples/clients/typescript"
        (self.package / "src").mkdir(parents=True)
        self.source = self.package / "src/client.ts"
        self.source.write_text("synthetic source")
        (self.package / "package.json").write_text('{"name":"test-client","version":"1.0.0"}')
        contract = self.root / "contracts/openapi/aethron-edge-v1.json"
        contract.parent.mkdir(parents=True)
        contract.write_text("{}")
        for name in ["package.json", "package-lock.json", "offline-consumer.mjs"]:
            (self.package / name).write_bytes(
                (ROOT / "examples/clients/typescript" / name).read_bytes()
            )
        self.pack_metadata = [{"filename": "test-client-1.0.0.tgz"}]
        self.actions = []
        self.after_install = lambda: None
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
                if arguments[1:3] == ["run", "build"]:
                    self.actions.append("build")
                    return subprocess.CompletedProcess(arguments, 0)
                if arguments[1] == "pack":
                    self.actions.append("pack")
                    self.assertIn("--offline", arguments)
                    self.assertIn("--ignore-scripts", arguments)
                    destination = Path(arguments[arguments.index("--pack-destination") + 1])
                    archive = destination / "test-client-1.0.0.tgz"
                    archive.write_bytes(b"fresh synthetic archive")
                    return subprocess.CompletedProcess(
                        arguments, 0, stdout=json.dumps(self.pack_metadata)
                    )
                self.actions.append("install")
                self.assertIn("ci", arguments)
                self.installed_archive = next(kwargs["cwd"].glob("*.tgz"))
                self.assertTrue((kwargs["cwd"] / "package-lock.json").is_file())
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
                self.after_install()
                return subprocess.CompletedProcess(arguments, 0)
            self.assertEqual(arguments[0], "node")
            if arguments[1].endswith("offline-consumer.mjs"):
                self.actions.append("lock")
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

    def test_missing_legacy_archive_does_not_block_fresh_build(self):
        self.archive.unlink()
        try:
            self.invoke(EMIT)
        except ValueError as error:
            self.fail(str(error))
        self.assertEqual(self.actions, ["build", "pack", "lock", "install"])

    def test_fresh_archive_and_inputs_are_bound_to_result(self):
        self.invoke(EMIT)
        self.assertEqual(self.actions, ["build", "pack", "lock", "install"])
        self.assertNotEqual(self.installed_archive, self.archive)
        record = json.loads(self.output.read_text())
        self.assertEqual(
            record["archive_sha256"], hashlib.sha256(b"fresh synthetic archive").hexdigest()
        )
        self.assertEqual(
            record["input_sha256"]["examples/clients/typescript/src/client.ts"],
            hashlib.sha256(b"synthetic source").hexdigest(),
        )

    def test_input_drift_during_install_rejects_before_server_start(self):
        self.after_install = lambda: self.source.write_text("changed source")
        with self.assertRaisesRegex(ValueError, "client_inputs_changed"):
            self.invoke(EMIT)
        self.assertEqual(self.lifecycle, [])
        self.assertFalse(self.output.exists())

    def test_archive_drift_during_install_rejects_before_server_start(self):
        self.after_install = lambda: self.installed_archive.write_bytes(b"changed archive")
        with self.assertRaisesRegex(ValueError, "client_archive_changed"):
            self.invoke(EMIT)
        self.assertEqual(self.lifecycle, [])
        self.assertFalse(self.output.exists())

    def test_failed_server_cleanup_does_not_publish_success(self):
        def fail_cleanup():
            raise RuntimeError("cleanup failed")

        self.service.HTTPService.tearDownClass = fail_cleanup
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            self.invoke(EMIT)
        self.assertFalse(self.output.exists())

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

    def test_invalid_pack_metadata_never_reaches_install(self):
        for metadata in [
            [],
            [{}, {}],
            [None],
            [{"filename": 1}],
            [{"filename": "../escape.tgz"}],
            [{"filename": "C:escape.tgz"}],
        ]:
            with self.subTest(metadata=metadata):
                self.actions.clear()
                self.pack_metadata = metadata
                with self.assertRaisesRegex(ValueError, "invalid_pack_result"):
                    self.invoke(EMIT)
                self.assertEqual(self.actions, ["build", "pack"])
                self.assertFalse(self.output.exists())

    def test_source_change_during_server_cleanup_rejects_result(self):
        stop = self.service.HTTPService.tearDownClass

        def change_source():
            stop()
            self.source.write_text("changed after observations")

        self.service.HTTPService.tearDownClass = change_source
        with self.assertRaisesRegex(ValueError, "client_inputs_changed"):
            self.invoke(EMIT)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.lifecycle, ["start", "stop"])

    def test_invalid_consumer_lock_never_installs_or_starts_server(self):
        (self.package / "package-lock.json").write_text('{"lockfileVersion":1}')
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(EMIT)
        self.assertEqual(self.actions, ["build", "pack", "lock"])
        self.assertEqual(self.lifecycle, [])
        self.assertFalse(self.output.exists())
