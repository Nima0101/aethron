"""Owned-process scheduling experiment, synthetic localhost traffic only."""

import argparse
import json
import multiprocessing as mp
import socket
import tempfile
import time
from pathlib import Path

from aethron_edge.config import ApplianceConfig
from aethron_edge.runtime.supervisor import ApplianceSupervisor
from aethron_edge.telemetry.signing import SigningTrust, provision_replay
from aethron_edge.telemetry.worker import TelemetryProfile, TelemetrySupervisor
from pymavlink.dialects.v20 import common


def send(port, stop, result):
    wall, cpu = time.monotonic_ns(), time.thread_time_ns()
    previous = wall
    gap = count = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while not stop.is_set():
            now = time.monotonic_ns()
            gap = max(gap, now - previous)
            previous = now
            encoder = common.MAVLink(None, srcSystem=1, srcComponent=2)
            encoder.seq = count % 256
            encoder.signing.secret_key = bytes(range(32))
            encoder.signing.sign_outgoing = True
            encoder.signing.link_id = 7
            encoder.signing.timestamp = 10_000_001 + count
            sock.sendto(
                common.MAVLink_attitude_message(10 + count, 0.1, 0.2, 0.3, 0, 0, 0).pack(encoder),
                ("127.0.0.1", port),
            )
            count += 1
            stop.wait(0.05)
    result.send(
        {
            "sent": count,
            "max_gap_ms": gap / 1e6,
            "wall_ms": (time.monotonic_ns() - wall) / 1e6,
            "cpu_ms": (time.thread_time_ns() - cpu) / 1e6,
        }
    )
    result.close()


class MeasuredAppliance(ApplianceSupervisor):
    def __init__(self):
        super().__init__()
        self.tick_wall = self.tick_cpu = self.tick_count = 0

    def tick(self, now):
        wall, cpu = time.monotonic_ns(), time.thread_time_ns()
        try:
            return super().tick(now)
        finally:
            self.tick_wall += time.monotonic_ns() - wall
            self.tick_cpu += time.thread_time_ns() - cpu
            self.tick_count += 1


def run(camera, fixture):
    ctx = mp.get_context("spawn")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        now = time.monotonic_ns()
        trust = SigningTrust(bytes(range(32)), 7, 10_000_000, now, now + 60_000_000_000)
        journal = root / "replay.db"
        provision_replay(journal, trust, system=1, component=2)
        telemetry = TelemetrySupervisor(TelemetryProfile(1, 2, port, str(journal)), trust)
        runtime = None
        if camera:
            runtime = MeasuredAppliance()
            config = ApplianceConfig.model_validate(
                {
                    "version": 1,
                    "status_file": str(root / "status.json"),
                    "profiles": [{"name": "camera", "driver": "replay", "address": str(fixture)}],
                }
            )
            runtime.boot(config)
        stop = ctx.Event()
        read, write = ctx.Pipe(duplex=False)
        sender = ctx.Process(target=send, args=(port, stop, write))
        try:
            telemetry.start()
            sender.start()
            write.close()
            start = previous = time.monotonic_ns()
            cpu = time.thread_time_ns()
            samples = auth = gap = 0
            first = None
            while time.monotonic_ns() - start < 8_000_000_000:
                now = time.monotonic_ns()
                gap = max(gap, now - previous)
                previous = now
                status = telemetry.snapshot()
                samples += 1
                if status["authenticated"]:
                    auth += 1
                    if first is None:
                        first = (now - start) / 1e6
                time.sleep(0.02)
            result = {
                "camera": camera,
                "reader_samples": samples,
                "authenticated_reads": auth,
                "first_auth_ms": first,
                "reader_max_gap_ms": gap / 1e6,
                "reader_cpu_ms": (time.thread_time_ns() - cpu) / 1e6,
                "telemetry": status,
            }
            if runtime:
                result["camera_ticks"] = {
                    "count": runtime.tick_count,
                    "wall_ms": runtime.tick_wall / 1e6,
                    "cpu_ms": runtime.tick_cpu / 1e6,
                }
        finally:
            stop.set()
            if sender.pid:
                sender.join(3)
                if sender.is_alive():
                    sender.terminate()
                    sender.join(3)
            telemetry.close()
            if runtime:
                runtime.shutdown()
        if read.poll(1):
            result["sender"] = read.recv()
        else:
            result["sender"] = "no_report"
        read.close()
        if sender.exitcode:
            raise RuntimeError("sender_failed")
        return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=Path, required=True)
    args = p.parse_args()
    for camera in [False, True, False]:
        print(json.dumps(run(camera, args.fixture)), flush=True)
