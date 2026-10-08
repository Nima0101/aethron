"""Worker-owned acquisition/inference; parent-owned trusted clock and core watchdog."""

import io
import json
import multiprocessing as mp
import queue
import time
from pathlib import Path

from aethron.temporal.replay import replay
from aethron.temporal.session import Session

from .calibration import CalibrationRecord
from .config import Profile
from .sources.base import SourceConfig, SourceFault
from .timebase import MappedFrame


def build_v3(
    frame: MappedFrame,
    proposals: list,
    calibration: CalibrationRecord,
    *,
    now_ns: int,
    contract="warn",
    lighting="daylight",
    mount_id="fixed",
    ego=None,
) -> bytes:
    f = frame.frame
    if not calibration.valid_for(f, now_ns // 1_000_000, mount_id):
        raise ValueError("calibration_expired")
    # Round exposure earlier, not later; uncertainty consumes the age budget.
    at = (frame.exposure_ns - frame.uncertainty_ns) // 1_000_000
    if not 0 <= now_ns // 1_000_000 - at <= 100:
        raise ValueError("clock_untrusted")
    payload = {
        "version": 3,
        "at_ms": at,
        "lighting": lighting,
        "evidence": f.evidence,
        "mode": "direct",
        "contract": contract,
        "scene_break": False,
        "ego": ego or {"dx": 0, "dy": 0, "variance": 0.05, "valid": False},
        "sensors": [
            {
                "kind": f.modality,
                "at_ms": at,
                "quality": "valid",
                "registered": True,
                "calibration_until_ms": calibration.valid_until_ms,
                "detections": proposals,
            }
        ],
    }
    return json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()


def _latest(channel, message):
    try:
        channel.put_nowait(message)
    except queue.Full:
        try:
            channel.get_nowait()
        except queue.Empty:
            return
        try:
            channel.put_nowait(message)
        except queue.Full:
            pass


def _worker(profile, channel, stop):
    source = None
    try:
        if profile.driver == "replay":
            data = Path(profile.address).read_bytes()
            if len(data) > 20 * 1024 * 1024:
                raise ValueError()
            list(replay(io.BytesIO(data)))  # Validate complete bounded fixture before activation.
            rows = [json.loads(line) for line in data.splitlines()]
            while not stop.is_set():
                for index, original in enumerate(rows):
                    if stop.is_set():
                        break
                    frame = json.loads(json.dumps(original))
                    now = time.monotonic_ns() // 1_000_000
                    delta = now - frame["at_ms"]
                    frame["at_ms"] = now
                    frame["contract"] = profile.contract
                    frame["scene_break"] = index == 0
                    for sensor in frame["sensors"]:
                        sensor["at_ms"] += delta
                        sensor["calibration_until_ms"] += delta
                    _latest(
                        channel,
                        {
                            "data": json.dumps(frame, separators=(",", ":")).encode(),
                            "reason": None,
                            "latency_ms": 0,
                        },
                    )
                    stop.wait(0.05)
            return
        import cv2
        import numpy as np

        from aethron.temporal.registration import estimate_translation
        from aethron.vision.yolox import RGBDetector

        from .sources.file import FileSource
        from .sources.rtsp import RTSPSource
        from .sources.uvc import UVCSource

        cv2.setNumThreads(1)
        detector = RGBDetector(profile.model, backend=profile.provider)
        source = {"file": FileSource, "uvc": UVCSource, "rtsp": RTSPSource}[profile.driver]()
        source.open(
            SourceConfig(profile.driver, profile.address, profile.backend, profile.calibration_id)
        )
        previous = None
        while not stop.is_set():
            frame = source.read(time.monotonic_ns() + 2_000_000_000)
            if isinstance(frame, SourceFault):
                _latest(channel, {"data": None, "reason": "source_lost", "latency_ms": 0})
                return
            pixels = np.frombuffer(frame.pixels, dtype=np.uint8).reshape(
                frame.height, frame.width, 3
            )
            if frame.width > 1280 or frame.height > 720:
                # Pinned detector requires <=1280x720; no implicit resize/calibration change.
                raise ValueError()
            proposals = detector.infer(pixels, lighting=profile.lighting)
            gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
            gray = cv2.resize(gray, (160, 120))
            pgm = b"P5\n160 120\n255\n" + gray.tobytes()
            ego = estimate_translation(previous, pgm) if previous else None
            previous = pgm
            # Generic OpenCV capture provides no qualified exposure clock. Inference
            # really runs, but its proposals never become current core evidence.
            _latest(
                channel,
                {
                    "data": None,
                    "reason": "clock_untrusted",
                    "latency_ms": (time.monotonic_ns() - frame.receive_ns) / 1e6,
                    "proposal_count": len(proposals),
                    "registration_valid": bool(ego and ego["valid"]),
                },
            )
    except Exception:
        _latest(channel, {"data": None, "reason": "model_error", "latency_ms": 0})
    finally:
        if source:
            source.close()


class RuntimePipeline:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.core = Session()
        self.process = None
        self.reason = "source_lost"
        self.processed = 0
        self.last_latency_ms = 0.0
        self.proposal_count = 0
        self.last_message_ns = 0

    def start(self):
        self.stop_worker()
        self.core.close()
        self.core = Session()
        ctx = mp.get_context("spawn")
        self.channel = ctx.Queue(maxsize=1)
        self.stop = ctx.Event()
        self.process = ctx.Process(target=_worker, args=(self.profile, self.channel, self.stop))
        self.process.start()
        self.started_ns = time.monotonic_ns()
        self.last_message_ns = self.started_ns

    def tick(self, now_ns):
        if self.process is None:
            return self.snapshot(now_ns)
        try:
            message = self.channel.get_nowait()
        except (queue.Empty, AttributeError):
            return self.snapshot(now_ns)
        self.processed += 1
        self.last_message_ns = now_ns
        self.reason = message["reason"]
        self.last_latency_ms = message["latency_ms"]
        self.proposal_count = message.get("proposal_count", 0)
        if message["data"] is not None:
            return self.core.step(message["data"], now_ms=now_ns // 1_000_000)
        return self.snapshot(now_ns)

    def snapshot(self, now_ns):
        return self.core.watchdog(now_ms=now_ns // 1_000_000)

    def stop_worker(self):
        if self.process is not None:
            self.stop.set()
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=1)
            self.process.close()
            self.process = None
            self.channel.close()
            self.channel.cancel_join_thread()

    def close(self):
        self.stop_worker()
        self.core.close()
