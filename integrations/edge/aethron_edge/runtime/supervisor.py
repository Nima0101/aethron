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
        try:
            self.thread.start()
        except Exception:
            # A thread that never started cannot be joined. Preserve ownership
            # if it did start, including a thread that has already finished.
            if self.thread.ident is None:
                self.thread = None
            raise
        return self.status(time.monotonic_ns())

    def _loop(self):
        while not self.stop.wait(0.01):
            self.tick(time.monotonic_ns())

    def tick(self, now_ns):
        with self.lock:
            for name, p in list(self.pipelines.items()):
                if name in self.recovering or name in self.faults:
                    continue
                try:
                    p.tick(now_ns)
                except Exception:
                    # A failed message/read is not fresh evidence and must not
                    # stop supervision of other profiles. Retire this scene
                    # immediately, then reap outside the watchdog without retry
                    # or publication of potentially private exception details.
                    self.faults.add(name)
                    self._recover(name, p, restart=False)
                    continue
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
            replacement = None
            try:
                pipeline.stop_worker()
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
                    if (
                        replacement is not None
                        and not self.stop.is_set()
                        and name not in self.faults
                    ):
                        self.pipelines[name] = replacement
                        return
                # Startup can outlive shutdown's bounded join or a scheduling
                # fault. Recovery still owns the unpublished worker and reaps it.
                if replacement is not None:
                    replacement.close()
            except Exception:
                # A failed recovery is terminal, not an indefinitely recovering
                # service. Never expose exception text from worker startup.
                with self.lock:
                    self.faults.add(name)
                if replacement is not None:
                    try:
                        replacement.close()
                    except Exception:
                        # Retain ownership so shutdown can retry cleanup.
                        with self.lock:
                            self.pipelines[name] = replacement
            finally:
                with self.lock:
                    self.recovering.discard(name)

        task = None
        try:
            task = threading.Thread(target=work, name="aethron-recovery", daemon=True)
            self.maintenance = [t for t in self.maintenance if t.is_alive()]
            task.start()
        except Exception:
            # A start error does not prove that work() never started. Retain
            # started tasks for shutdown; only their finally retires recovery.
            # Unstarted tasks cannot be joined and leave the original owner.
            self.faults.add(name)
            if task is not None and task.ident is not None:
                self.maintenance.append(task)
            else:
                self.recovering.discard(name)
        else:
            # The caller holds self.lock, so shutdown cannot miss a started task.
            self.maintenance.append(task)

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
        cleanup_failed = False

        def attempt(operation, **kwargs):
            nonlocal cleanup_failed
            try:
                operation(**kwargs)
            except Exception:
                # Keep ownership for retry, but never abandon later resources
                # or retain potentially private native exception diagnostics.
                cleanup_failed = True

        def join(task, timeout):
            nonlocal cleanup_failed
            task.join(timeout=timeout)
            # A timed join returns None even when the thread still owns work.
            # Keep its handle for retry and never publish a completed stop.
            if task.is_alive():
                cleanup_failed = True

        with self.lock:
            self.stop.set()
            # Withdraw every public scene before any thread join or telemetry
            # cleanup can wait. Keep worker ownership for the cleanup below;
            # queued observations must not revive a scene during that wait.
            for pipeline in self.pipelines.values():
                attempt(pipeline.withdraw_scene)
        if self.thread:
            attempt(join, task=self.thread, timeout=2)
        for task in self.maintenance:
            attempt(join, task=task, timeout=4)
        for source in self.telemetry.values():
            attempt(source.close)
        with self.lock:
            for pipeline in self.pipelines.values():
                attempt(pipeline.close)
            if cleanup_failed:
                self.faults.add("shutdown_cleanup")
            if self.config is not None:
                try:
                    result = self.status(time.monotonic_ns())
                    result["state"] = "fault" if cleanup_failed else "stopped"
                    publish_status(Path(self.config.status_file), result)
                except Exception:
                    # Diagnostics can fail after resource cleanup. Preserve the
                    # fixed failure boundary and allow an explicit retry; never
                    # invent a successful status or expose the reporting error.
                    cleanup_failed = True
                    self.faults.add("shutdown_cleanup")
        if cleanup_failed:
            raise RuntimeError("appliance_cleanup_failed") from None
