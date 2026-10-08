"""Guest-only SIL probe. No network, login, viewer or provisioning channel needed."""

import json
import os
import resource
import signal
import subprocess
import time
from pathlib import Path


def emit(value):
    with open("/dev/ttyAMA0", "w") as serial:
        serial.write("AETHRON_SIL " + json.dumps(value, sort_keys=True) + "\n")


def run():
    root = Path("/var/lib/aethron-sil")
    root.mkdir(exist_ok=True)
    count = root / "boots"
    boot = int(count.read_text()) + 1 if count.exists() else 1
    count.write_text(str(boot))
    start = time.monotonic()
    samples = []
    processed = []
    failures = []
    injected = False
    updated = False
    update_task = None
    update_task_start = None
    update_log = None
    update_stages = set()
    updated_pid = None
    update_verified = False
    update_started_ms = None
    recovered_before_update = False
    processed_at_fault = None
    rss = []
    max_status_bytes = 0
    duration = 45 if boot == 1 else 3600
    emit({"event": "boot", "boot": boot, "network": "no_virtual_nic", "login": False, "viewers": 0})
    while time.monotonic() - start < duration:
        time.sleep(1)
        try:
            status = json.loads(Path("/var/lib/aethron/status.json").read_text())
            if status["status_expires_ms"] < time.monotonic_ns() // 1_000_000:
                failures.append("status_expired")
            samples.append(status["last_processing_ms"])
            processed.append(status["processed"])
            max_status_bytes = max(
                max_status_bytes, Path("/var/lib/aethron/status.json").stat().st_size
            )
            memory = Path("/sys/fs/cgroup/system.slice/aethron.service/memory.current")
            if memory.exists():
                rss.append(int(memory.read_text()))
            if not injected and boot > 1 and time.monotonic() - start > 120:
                main = subprocess.check_output(
                    ["systemctl", "show", "--property=MainPID", "--value", "aethron.service"],
                    text=True,
                ).strip()
                children = Path("/proc/" + main + "/task/" + main + "/children").read_text().split()
                for child in children:
                    if b"spawn_main" in Path("/proc/" + child + "/cmdline").read_bytes():
                        os.kill(int(child), signal.SIGKILL)
                processed_at_fault = status["processed"]
                injected = True
                emit({"event": "worker_fault_injected", "boot": boot})
            if (
                processed_at_fault is not None
                and not updated
                and status["processed"] > processed_at_fault + 10
            ):
                recovered_before_update = True
            if boot > 1 and update_task is None and time.monotonic() - start > 240:
                if not recovered_before_update:
                    raise RuntimeError("worker_did_not_recover_before_update")
                update_log = (root / "update.log").open("w+")
                update_task = subprocess.Popen(
                    ["/opt/aethron/venv/bin/python", "-B", "/opt/aethron-sil/update_probe.py"],
                    stdout=update_log,
                    stderr=update_log,
                )
                update_task_start = time.monotonic()
            if update_task is not None and not updated:
                update_log.flush()
                update_log.seek(0)
                lines = update_log.read(65536).splitlines()
                for line in lines:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    stage = row.get("stage")
                    if stage and stage not in update_stages:
                        emit({"event": "update_stage", "boot": boot, "stage": stage})
                        update_stages.add(stage)
                code = update_task.poll()
                if code is None and time.monotonic() - update_task_start > 600:
                    update_task.kill()
                    update_task.wait(timeout=10)
                    raise RuntimeError("offline_update_timeout")
                if code is not None:
                    if code != 0:
                        raise RuntimeError("offline_update_failed")
                    summary = json.loads(lines[-1])
                    if summary.get("updated") is not True:
                        raise RuntimeError("offline_update_incomplete")
                    emit(
                        {
                            "event": "offline_update",
                            "boot": boot,
                            "elapsed_s": time.monotonic() - update_task_start,
                            **summary,
                        }
                    )
                    subprocess.run(
                        ["systemctl", "restart", "aethron.service"], check=True, timeout=30
                    )
                    update_started_ms = time.monotonic_ns() // 1_000_000
                    updated = True
                    update_log.close()
            if updated and not update_verified:
                updated_pid = subprocess.check_output(
                    ["systemctl", "show", "--property=MainPID", "--value", "aethron.service"],
                    text=True,
                ).strip()
                if updated_pid != "0":
                    args = Path("/proc/" + updated_pid + "/cmdline").read_bytes()
                    if (
                        b"/updates/2-" in args
                        and status["processed"] > 10
                        and status["emitted_ms"] >= update_started_ms
                    ):
                        update_verified = True
                        emit({"event": "updated_runtime_processing", "boot": boot, "version": 2})
            if len(samples) % 60 == 0:
                emit(
                    {
                        "event": "progress",
                        "boot": boot,
                        "seconds": round(time.monotonic() - start),
                        "processed": status["processed"],
                        "fault_count": status["fault_count"],
                    }
                )
        except (OSError, ValueError, KeyError):
            failures.append("status_unavailable")
    ready = bool(processed and processed[-1] > processed[0])
    ordered = sorted(samples)

    def quantile(q):
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * q))] if ordered else None

    result = {
        "event": "result",
        "boot": boot,
        "seconds": time.monotonic() - start,
        "processing_continued": ready,
        "samples": len(samples),
        "latency_ms": {
            "p50": quantile(0.5),
            "p95": quantile(0.95),
            "p99": quantile(0.99),
            "max": max(samples, default=None),
        },
        "status_unavailable_samples": failures.count("status_unavailable"),
        "status_expired_samples": failures.count("status_expired"),
        "worker_fault_injected": injected,
        "offline_update_activated": updated,
        "updated_runtime_processing": update_verified,
        "processing_resumed_after_fault": recovered_before_update,
        "hardware_qualified": False,
        "sensor": "synthetic_multimodal_proposals",
        "rss_probe_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "service_cgroup_peak_bytes": max(rss, default=None),
        "status_max_bytes": max_status_bytes,
        "log_bytes": sum(
            p.stat().st_size for p in Path("/run/log/journal").rglob("*") if p.is_file()
        ),
    }
    (root / f"result-{boot}.json").write_text(json.dumps(result, indent=2))
    emit(result)
    subprocess.run(["systemctl", "reboot" if boot == 1 else "poweroff"], check=True)


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        emit({"event": "probe_failed", "error_type": type(error).__name__})
        raise
