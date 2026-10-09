"""Processing must precede HTTP import; the CLI owns workers through early failures."""

import asyncio
import builtins
import json
import signal
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.config import ApplianceConfig
from aethron_edge.runtime.supervisor import ApplianceSupervisor

ROOT = Path(__file__).resolve().parents[2]


def config(directory):
    return ApplianceConfig.model_validate(
        {
            "version": 1,
            "status_file": str(Path(directory) / "status.json"),
            "profiles": [
                {
                    "name": "bench",
                    "driver": "replay",
                    "address": str(ROOT / "examples/temporal-blackout.jsonl"),
                }
            ],
        }
    )


class Startup(unittest.TestCase):
    def exercise(self, outcome):
        from aethron_edge.runtime.entrypoint import run

        original_import = builtins.__import__
        handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        runtime = ApplianceSupervisor()
        workers = []
        with tempfile.TemporaryDirectory() as directory:
            settings = config(directory)

            def serve(settings, *, supervisor):
                self.assertIs(supervisor, runtime)

            def delayed_import(name, *args, **kwargs):
                if name == "service.app":
                    self.assertIsNotNone(runtime.thread)
                    workers.extend(p.process for p in runtime.pipelines.values())
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        path = Path(settings.status_file)
                        if path.exists() and json.loads(path.read_text())["processed"] >= 3:
                            break
                        time.sleep(0.02)
                    else:
                        self.fail("processing/status unavailable while HTTP import waits")
                    if outcome == "import_error":
                        raise ImportError("test-only HTTP dependency failure")
                    if outcome == "signal":
                        signal.raise_signal(signal.SIGTERM)
                    return SimpleNamespace(serve=serve)
                return original_import(name, *args, **kwargs)

            with patch("aethron_edge.runtime.entrypoint.ApplianceSupervisor", return_value=runtime):
                with patch("builtins.__import__", side_effect=delayed_import):
                    if outcome == "import_error":
                        with self.assertRaises(ImportError):
                            run(settings)
                    elif outcome == "signal":
                        with self.assertRaises(SystemExit) as stopped:
                            run(settings)
                        self.assertEqual(stopped.exception.code, 128 + signal.SIGTERM)
                    else:
                        run(settings)
            self.assertTrue(workers)
            self.assertTrue(all(worker._closed for worker in workers))
            self.assertTrue(all(p.process is None for p in runtime.pipelines.values()))
            self.assertFalse(runtime.thread.is_alive())
            self.assertEqual(json.loads(Path(settings.status_file).read_text())["state"], "stopped")
        for sig, handler in handlers.items():
            self.assertIs(signal.getsignal(sig), handler)

    def test_processing_before_delayed_api_import_and_same_runtime_handoff(self):
        self.exercise("serve")

    def test_import_failure_reaps_workers(self):
        self.exercise("import_error")

    def test_sigterm_during_import_reaps_workers_and_restores_handlers(self):
        self.exercise("signal")

    def test_partial_boot_failure_cleans_up_without_loading_http(self):
        from aethron_edge.runtime.entrypoint import run

        runtime = ApplianceSupervisor()
        boot = runtime.boot
        workers = []

        def fail_after_start(settings):
            boot(settings)
            workers.extend(p.process for p in runtime.pipelines.values())
            raise OSError("test-only partial startup failure")

        with tempfile.TemporaryDirectory() as directory:
            settings = config(directory)
            with patch("aethron_edge.runtime.entrypoint.ApplianceSupervisor", return_value=runtime):
                with patch.object(runtime, "boot", side_effect=fail_after_start):
                    with self.assertRaises(OSError):
                        run(settings)
            self.assertTrue(workers)
            self.assertTrue(all(worker._closed for worker in workers))
            self.assertFalse(runtime.thread.is_alive())
            self.assertEqual(json.loads(Path(settings.status_file).read_text())["state"], "stopped")

    def test_termination_before_boot_initialization_preserves_exit(self):
        from aethron_edge.runtime.entrypoint import run

        runtime = ApplianceSupervisor()
        with tempfile.TemporaryDirectory() as directory:
            with patch("aethron_edge.runtime.entrypoint.ApplianceSupervisor", return_value=runtime):
                with patch.object(
                    runtime, "boot", side_effect=lambda _: signal.raise_signal(signal.SIGTERM)
                ):
                    with self.assertRaises(SystemExit) as stopped:
                        run(config(directory))
            self.assertEqual(stopped.exception.code, 128 + signal.SIGTERM)
            self.assertFalse(Path(directory, "status.json").exists())

    def test_invalid_signature_precedes_api_or_runtime_import(self):
        from aethron_edge.cli import main

        original_import = builtins.__import__
        imports = []

        def record(name, *args, **kwargs):
            imports.append(name)
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            settings = config(directory)
            with patch("sys.argv", ["aethron-edge", "run", "--config", "invalid.json"]):
                with patch("aethron_edge.config.load_config", return_value=settings):
                    with patch(
                        "aethron_edge.runtime.updates.verify_configuration",
                        side_effect=ValueError("invalid_bundle"),
                    ):
                        with patch("builtins.__import__", side_effect=record):
                            with self.assertRaises(SystemExit) as rejected:
                                main()
            self.assertEqual(rejected.exception.code, 2)
        self.assertNotIn("service.app", imports)
        self.assertNotIn("runtime.entrypoint", imports)

    def test_http_lifespan_preserves_external_runtime_ownership(self):
        from aethron_edge.service.app import create_app

        with tempfile.TemporaryDirectory() as directory:
            runtime = Mock()
            app = create_app(config(directory), supervisor=runtime)

            async def lifespan():
                async with app.router.lifespan_context(app):
                    pass

            asyncio.run(lifespan())
            runtime.boot.assert_not_called()
            runtime.shutdown.assert_not_called()

    def test_http_lifespan_default_still_owns_runtime(self):
        from aethron_edge.service.app import create_app

        with tempfile.TemporaryDirectory() as directory:
            settings = config(directory)
            with patch("aethron_edge.service.app.ApplianceSupervisor") as factory:
                app = create_app(settings)

                async def lifespan():
                    async with app.router.lifespan_context(app):
                        pass

                asyncio.run(lifespan())
                factory.return_value.boot.assert_called_once_with(settings)
                factory.return_value.shutdown.assert_called_once_with()
