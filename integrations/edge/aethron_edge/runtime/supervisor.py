"""One bounded watchdog loop supervises workers even with zero HTTP viewers."""

import threading
import time
from collections import deque
from pathlib import Path

from ..pipeline import RuntimePipeline
from .health import publish_status


class ApplianceSupervisor:
    def __init__(self):
        self.pipelines = {}
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
        self.config = config
        self.started_ns = time.monotonic_ns()
        self.pipelines = {p.name: RuntimePipeline(p) for p in config.profiles}
        self.restarts = {name: deque(maxlen=5) for name in self.pipelines}
        self.next_restart = dict.fromkeys(self.pipelines, 0)
        Path(config.status_file).parent.mkdir(parents=True, exist_ok=True)
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
                failed = p.process is not None and (
                    not p.process.is_alive()
                    or now_ns - p.last_message_ns
                    > (10_000_000_000 if p.profile.driver == "replay" else 60_000_000_000)
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
        pipeline.core.close()

        def work():
            pipeline.stop_worker()
            replacement = None
            if restart and not self.stop.is_set():
                replacement = RuntimePipeline(pipeline.profile)
                replacement.processed = pipeline.processed
                replacement.inferences = pipeline.inferences
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
        return {
            "version": 1,
            "mode": self.config.runtime_mode,
            "state": "fault" if self.faults else "recovering" if self.recovering else "running",
            "scene_state": "UNKNOWN",
            "qualified": False,
            "emitted_ms": now_ns // 1_000_000,
            "status_expires_ms": now_ns // 1_000_000 + 2000,
            "uptime_ms": max(0, (now_ns - self.started_ns) // 1_000_000),
            "processed": sum(p.processed for p in self.pipelines.values()),
            "inferences": sum(p.inferences for p in self.pipelines.values()),
            "fault_count": len(self.faults),
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
        with self.lock:
            for pipeline in self.pipelines.values():
                pipeline.close()
            result = self.status(time.monotonic_ns())
            result["state"] = "stopped"
            try:
                publish_status(Path(self.config.status_file), result)
            except OSError:
                pass
