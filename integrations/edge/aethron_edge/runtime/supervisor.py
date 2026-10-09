"""One bounded watchdog loop supervises workers even with zero HTTP viewers."""

import threading
import time
from collections import deque
from pathlib import Path

from ..pipeline import RuntimePipeline
from .health import publish_status


class ApplianceSupervisor:
    def __init__(self):
        self.config = None
        self.pipelines = {}
        self.telemetry = {}
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.faults = set()
        self.restarts = {}
        self.next_restart = {}
        self.last_status = 0
        self.started_ns = 0
        self.recovering = set()
        self.maintenance = []

    def boot(self, config):
        if self.config is not None or self.stop.is_set():
            raise ValueError("appliance_already_started")
        self.config = config
        self.started_ns = time.monotonic_ns()
        if config.telemetry:
            from ..telemetry.boot_authority import issue_boot_trust
            from ..telemetry.provisioning import load_boot_policy, load_trust
            from ..telemetry.worker import TelemetryProfile, TelemetrySupervisor

            for item in config.telemetry:
                policy = None
                if item.clock_policy_file is not None:
                    policy = load_boot_policy(
                        item.clock_policy_file, system=item.system_id, component=item.component_id
                    )
                    trust = issue_boot_trust(item.replay_file, policy)
                else:
                    trust = load_trust(
                        item.credential_file, system=item.system_id, component=item.component_id
                    )
                self.telemetry[item.name] = TelemetrySupervisor(
                    TelemetryProfile(
                        item.system_id, item.component_id, item.port, item.replay_file
                    ),
                    trust,
                    clock_policy=policy,
                )
        self.pipelines = {p.name: RuntimePipeline(p) for p in config.profiles}
        self.restarts = {name: deque(maxlen=5) for name in self.pipelines}
        self.next_restart = dict.fromkeys(self.pipelines, 0)
        Path(config.status_file).parent.mkdir(parents=True, exist_ok=True)
        for telemetry in self.telemetry.values():
            telemetry.start()
        for pipeline in self.pipelines.values():
            pipeline.start()
        self.thread = threading.Thread(target=self._loop, name="aethron-watchdog", daemon=True)
        self.thread.start()
        return self.status(time.monotonic_ns())

    def _loop(self):
        while not self.stop.wait(0.01):
            self.tick(time.monotonic_ns())

    def tick(self, now_ns):
        with self.lock:
            for name, p in list(self.pipelines.items()):
                if name in self.recovering or name in self.faults:
                    continue
                p.tick(now_ns)
                if p.ros_guard is not None and p.ros_guard.closed:
                    # A revoked boot authority cannot recover through a worker
                    # restart. Withdraw immediately and reap outside the watchdog.
                    self.faults.add(name)
                    self._recover(name, p, restart=False)
                    continue
                failed = p.process is not None and (
                    not p.process.is_alive()
                    or now_ns - p.last_message_ns
                    > (
                        10_000_000_000
                        if p.profile.driver in {"replay", "sensor-replay", "sensor-ros"}
                        else 60_000_000_000
                    )
                )
                if failed and name not in self.faults and now_ns >= self.next_restart[name]:
                    attempts = self.restarts[name]
                    while attempts and now_ns - attempts[0] > 60_000_000_000:
                        attempts.popleft()
                    if len(attempts) >= 5:
                        self.faults.add(name)
                        # Expiry is immediate; shutdown occurs outside a core step.
                        self._recover(name, p, restart=False)
                    else:
                        attempts.append(now_ns)
                        self.next_restart[name] = now_ns + 2_000_000_000
                        self._recover(name, p, restart=True)
            result = self.status(now_ns)
            if now_ns - self.last_status >= 1_000_000_000:
                try:
                    publish_status(Path(self.config.status_file), result)
                except OSError:
                    self.faults.add("status_storage")
                self.last_status = now_ns
            return result

    def _recover(self, name, pipeline, *, restart):
        self.recovering.add(name)
        pipeline.last_result = None
        pipeline.sensor_expires_ns = 0
        pipeline.core.close()

        def work():
            pipeline.stop_worker()
            replacement = None
            if restart and not self.stop.is_set():
                replacement = RuntimePipeline(
                    pipeline.profile, ros_grant=pipeline.ros_grant, ros_guard=pipeline.ros_guard
                )
                replacement.processed = pipeline.processed
                replacement.inferences = pipeline.inferences
                replacement.sensor_batches = pipeline.sensor_batches
                replacement.prior_drops = pipeline.drop_counts()
                replacement.start()
            with self.lock:
                if replacement is not None:
                    self.pipelines[name] = replacement
                self.recovering.discard(name)

        task = threading.Thread(target=work, name="aethron-recovery", daemon=True)
        self.maintenance = [t for t in self.maintenance if t.is_alive()]
        self.maintenance.append(task)
        task.start()

    def status(self, now_ns):
        telemetry = {name: source.snapshot() for name, source in self.telemetry.items()}
        fault_count = len(self.faults) + sum(s["state"] == "fault" for s in telemetry.values())
        return {
            "version": 1,
            "mode": self.config.runtime_mode,
            "state": "fault" if fault_count else "recovering" if self.recovering else "running",
            "scene_state": "UNKNOWN",
            "qualified": False,
            "emitted_ms": now_ns // 1_000_000,
            "status_expires_ms": now_ns // 1_000_000 + 2000,
            "uptime_ms": max(0, (now_ns - self.started_ns) // 1_000_000),
            "processed": sum(p.processed for p in self.pipelines.values()),
            "inferences": sum(p.inferences for p in self.pipelines.values()),
            "sensors": {
                name: p.sensor_status(now_ns)
                for name, p in self.pipelines.items()
                if p.profile.driver in {"sensor-replay", "sensor-ros"}
            },
            "telemetry": telemetry,
            "drops": {
                key: sum(p.drop_counts()[key] for p in self.pipelines.values())
                for key in ("capture_sequence_gaps", "mailbox_overwritten", "mailbox_rejected")
            },
            "fault_count": fault_count,
            "restarts": sum(len(q) for q in self.restarts.values()),
            "last_processing_ms": max(
                (p.last_latency_ms for p in self.pipelines.values()), default=0
            ),
        }

    def snapshot(self, profile):
        with self.lock:
            return self.pipelines[profile].snapshot(time.monotonic_ns())

    def shutdown(self, reason="maintenance"):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        for task in self.maintenance:
            task.join(timeout=4)
        for source in self.telemetry.values():
            source.close()
        with self.lock:
            for pipeline in self.pipelines.values():
                pipeline.close()
            if self.config is None:
                return
            result = self.status(time.monotonic_ns())
            result["state"] = "stopped"
            try:
                publish_status(Path(self.config.status_file), result)
            except OSError:
                pass
