"""Guest-only signed CLI lifecycle check. Source-clock injection never changes OS time."""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ros_fixture import DepthFixture


def run_scenario(config_path, *, python=sys.executable, service=None):
    from aethron_edge.config import load_config
    from aethron_edge.sensors.ros_authority import read_ros_manifest

    config = load_config(config_path)
    if len(config.profiles) != 1 or config.profiles[0].driver != "sensor-ros":
        raise ValueError("isolated_ros_fixture_required")
    profile = config.profiles[0]
    manifest = read_ros_manifest(profile)
    if (
        manifest.renewal != "software_fixture"
        or manifest.valid_for_ns != 4_000_000_000
        or manifest.clock_drift_budget_ns != 1_000_000
    ):
        raise ValueError("bounded_synthetic_fixture_required")
    status_path = Path(config.status_file)
    process = None
    floor_ms = 0
    observed = {}

    def read():
        nonlocal observed
        if process.poll() is not None:
            raise RuntimeError("fixture_service_exited")
        try:
            with status_path.open("rb") as stream:
                status = json.loads(stream.read(4097))
            now = time.monotonic_ns() // 1_000_000
            emitted = status["emitted_ms"]
            if not (floor_ms <= emitted <= now <= status["status_expires_ms"] <= emitted + 2000):
                return None
            if status["qualified"] is not False or status["scene_state"] != "UNKNOWN":
                raise RuntimeError("fixture_semantic_promotion")
            row = status["sensors"][profile.name]
            if row["source_evidence"] != "external_unverified" or row["qualified"] is not False:
                raise RuntimeError("fixture_provenance_changed")
            observed = {
                k: row[k]
                for k in ("batches", "available", "authority_generation", "authority_fault")
            }
            return emitted, row
        except (OSError, ValueError, KeyError):
            return None

    def wait(predicate, seconds, *, fault=None):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            sample = read()
            if sample:
                _, row = sample
                if row["authority_fault"] not in (None, fault):
                    raise RuntimeError("unexpected_ros_fault:" + str(row["authority_fault"]))
                if predicate(row):
                    return row
            time.sleep(0.02)
        raise RuntimeError("fixture_deadline:" + json.dumps(observed, sort_keys=True))

    def no_revival(row):
        anchor = (row["batches"], row["authority_generation"], row["authority_fault"])
        samples = set()
        start = time.monotonic_ns() // 1_000_000
        deadline = time.monotonic() + 2.2
        while time.monotonic() < deadline:
            value = read()
            if value and value[0] >= start:
                emitted, current = value
                if (
                    current["available"]
                    or current["state"] != "fault"
                    or (
                        current["batches"],
                        current["authority_generation"],
                        current["authority_fault"],
                    )
                    != anchor
                ):
                    raise RuntimeError("revoked_authority_revived")
                samples.add(emitted)
            time.sleep(0.02)
        if len(samples) < 2:
            raise RuntimeError("revocation_observation_missing")

    def shutdown():
        if service is not None:
            service.stop()
            return
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise RuntimeError("fixture_shutdown_timeout") from None

    def start(log):
        nonlocal process, floor_ms
        status_path.unlink(missing_ok=True)
        floor_ms = time.monotonic_ns() // 1_000_000
        if service is not None:
            process = service
            service.start()
            return
        process = subprocess.Popen(
            [python, "-I", "-m", "aethron_edge", "run", "--config", str(config_path)],
            stdout=log,
            stderr=log,
        )

    with (
        DepthFixture(
            domain_id=manifest.domain_id,
            topic=manifest.topic,
            camera_info_topic=manifest.camera_info_topic,
        ) as fixture,
        tempfile.TemporaryFile() as log,
    ):
        try:
            start(log)
            wait(
                lambda r: r["available"] and r["batches"] >= 3 and r["authority_generation"] >= 1,
                15,
            )
            fixture.set_mode("pause")
            lost = wait(
                lambda r: r["state"] == "fault" and not r["available"], 6, fault="authority_expired"
            )
            if lost["authority_fault"] != "authority_expired":
                raise RuntimeError("wrong_source_loss_reason")
            fixture.set_mode("publish")
            no_revival(lost)
            shutdown()
            start(log)  # Explicit signed service restart; no hidden grant reset.
            wait(lambda r: r["available"] and r["batches"] >= 3, 15)
            fixture.set_mode("rewind")
            broken = wait(
                lambda r: r["state"] == "fault" and not r["available"],
                4,
                fault="source_clock_discontinuity",
            )
            if broken["authority_fault"] != "source_clock_discontinuity":
                raise RuntimeError("wrong_clock_loss_reason")
            fixture.set_mode("publish")
            no_revival(broken)
        finally:
            shutdown()
    return {
        "processing_observed": True,
        "source_expiry_verified": True,
        "reconnect_cannot_revive": True,
        "explicit_restart_revalidated": True,
        "source_rewind_verified": True,
        "clock_restore_cannot_revive": True,
        "continuous_availability_qualified": False,
        "hardware_qualified": False,
        "scene_state": "UNKNOWN",
        "viewers": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run_scenario(args.config), sort_keys=True))
