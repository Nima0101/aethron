"""Raw processing cannot borrow proposal counters or stale status for boot evidence."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SensorBootEvidence(unittest.TestCase):
    def setUp(self):
        module = load("sensor_probe", "packaging/appliance/image/sensor_probe.py")
        self.probe = module.SensorEvidence({"raw-depth": "recorded"})

    def sample(self, batches, at=1000, **change):
        value = {
            "emitted_ms": at,
            "status_expires_ms": at + 2000,
            "scene_state": "UNKNOWN",
            "qualified": False,
            "processed": 999999,
            "sensors": {
                "raw-depth": {
                    "batches": batches,
                    "available": True,
                    "state": "processing",
                    "source_evidence": "recorded",
                    "qualified": False,
                }
            },
        }
        value.update(change)
        return value

    def test_proposals_stale_status_and_missing_sensor_cannot_prove_processing(self):
        for value, now in (
            (self.sample(50, sensors={}), 1000),
            (self.sample(50), 3001),
            (self.sample(50, at=1001), 1000),
            (self.sample(50, qualified=True), 1000),
        ):
            self.probe.observe(value, now)
        result = self.probe.result()["raw-depth"]
        self.assertEqual(result["batches_observed"], 0)
        self.assertFalse(result["processing_observed"])
        self.assertFalse(result["processing_resumed_after_fault"])

    def test_recovery_and_updated_service_need_new_raw_activity(self):
        self.probe.observe(self.sample(20), 1000)
        self.probe.mark_fault()
        self.probe.observe(self.sample(20, at=1100), 1100)
        self.assertFalse(self.probe.recovered())
        self.probe.observe(self.sample(31, at=1200), 1200)
        self.assertTrue(self.probe.recovered())
        self.probe.mark_update(1300)
        self.probe.observe(self.sample(500, at=1299), 1300)
        self.assertFalse(self.probe.updated())
        self.probe.observe(self.sample(0, at=1400), 1400)
        self.assertFalse(self.probe.updated())
        self.probe.observe(self.sample(11, at=1500), 1500)
        self.assertTrue(self.probe.updated())
        result = self.probe.result()["raw-depth"]
        self.assertTrue(result["processing_observed"])
        self.assertTrue(result["processing_resumed_after_fault"])
        self.assertTrue(result["updated_runtime_processing"])
        self.assertEqual(result["batches_observed"], 42)

    def test_faults_and_unavailable_samples_are_retained_not_promoted(self):
        value = self.sample(20)
        sensor = value["sensors"]["raw-depth"]
        sensor.update(available=False, state="fault")
        self.probe.observe(value, 1000)
        result = self.probe.result()["raw-depth"]
        self.assertEqual(result["fault_samples"], 1)
        self.assertEqual(result["unavailable_samples"], 1)
        self.assertFalse(result["processing_observed"])

    def test_wrong_provenance_boolean_counts_and_duplicate_status_rejected(self):
        for field, value in (("source_evidence", "external_unverified"), ("batches", True)):
            status = self.sample(20)
            status["sensors"]["raw-depth"][field] = value
            self.probe.observe(status, 1000)
        self.assertFalse(self.probe.result()["raw-depth"]["processing_observed"])
        self.probe.observe(self.sample(20), 1000)
        self.probe.mark_fault()
        self.probe.observe(self.sample(50), 1000)
        self.assertFalse(self.probe.recovered())

    def test_early_activity_does_not_prove_processing_at_end_of_soak(self):
        self.probe.observe(self.sample(20), 1000)
        self.assertTrue(self.probe.result(1000)["raw-depth"]["processing_at_end"])
        self.assertFalse(self.probe.result(3001)["raw-depth"]["processing_at_end"])

    def test_guest_inputs_provision_actual_bound_raw_recording(self):
        import json
        import tempfile

        from aethron_edge.config import load_config
        from aethron_edge.sensors.provisioning import load_manifest, validate_recording

        prepare = load("image_prepare", "packaging/appliance/image/prepare.py")
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp)
            expected = prepare.stage_inputs(context)
            config = load_config(context / "appliance.json")
            raw = [p for p in config.profiles if p.driver == "sensor-replay"]
            self.assertEqual([p.name for p in raw], ["raw-depth"])
            self.assertEqual(expected, {"raw-depth": "recorded"})
            self.assertEqual(json.loads((context / "probe-profiles.json").read_text()), expected)
            manifest = load_manifest(Path(raw[0].sensor_manifest))
            self.assertTrue(manifest.loop)
            validate_recording(Path(raw[0].address), manifest)
            self.assertTrue((context / "sensor_probe.py").is_file())

    def test_staged_profiles_process_and_raw_worker_recovers_without_viewers(self):
        import tempfile
        import time

        from aethron_edge.config import load_config
        from aethron_edge.runtime.supervisor import ApplianceSupervisor

        prepare = load("image_prepare", "packaging/appliance/image/prepare.py")
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp)
            prepare.stage_inputs(context)
            config = load_config(context / "appliance.json")
            config.status_file = str(context / "status.json")
            runtime = ApplianceSupervisor()
            try:
                runtime.boot(config)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    with runtime.lock:
                        self.probe.observe(
                            runtime.status(time.monotonic_ns()), time.monotonic_ns() // 1_000_000
                        )
                    if self.probe.result()["raw-depth"]["processing_observed"]:
                        break
                    time.sleep(0.02)
                self.assertTrue(
                    self.probe.result()["raw-depth"]["processing_observed"],
                    {
                        "observed": self.probe.result(),
                        "runtime": runtime.status(time.monotonic_ns()),
                    },
                )
                with runtime.lock:
                    old = runtime.pipelines["raw-depth"]
                    before_other = runtime.pipelines["sil"].processed
                    self.probe.mark_fault()
                    old.process.terminate()
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    with runtime.lock:
                        self.probe.observe(
                            runtime.status(time.monotonic_ns()), time.monotonic_ns() // 1_000_000
                        )
                    if self.probe.recovered():
                        break
                    time.sleep(0.02)
                self.assertTrue(self.probe.recovered())
                self.assertIsNot(runtime.pipelines["raw-depth"], old)
                self.assertGreater(runtime.pipelines["sil"].processed, before_other)
                self.assertEqual(runtime.snapshot("raw-depth")["state"], "UNKNOWN")
            finally:
                runtime.shutdown()
