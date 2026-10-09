"""Worker-owned acquisition/inference; parent-owned trusted clock and core watchdog."""

import copy
import json
import multiprocessing as mp
import os
import queue
import signal
import time
from dataclasses import asdict
from pathlib import Path

from aethron.temporal.replay import replay
from aethron.temporal.session import Session

from .calibration import CalibrationRecord
from .config import Profile
from .mailbox import Mailbox, StopToken
from .process_tree import own_descendants
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
    # Validate the original nanosecond values before arithmetic can coerce them.
    if any(
        type(value) is not int or value < 0
        for value in (now_ns, frame.exposure_ns, frame.uncertainty_ns)
    ):
        raise ValueError("clock_untrusted")
    f = frame.frame
    if not calibration.valid_for(f, now_ns // 1_000_000, mount_id):
        raise ValueError("calibration_expired")
    # Round exposure earlier, not later; uncertainty consumes the age budget.
    at = (frame.exposure_ns - frame.uncertainty_ns) // 1_000_000
    if at < 0 or not 0 <= now_ns // 1_000_000 - at <= 100:
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
        # A busy reader/writer drops this new message. Never consume the previous
        # unread value here: overwrite and rejection counters stay unambiguous.
        pass


def _load_replay_rows(path, stop):
    """Validate once from bounded lines; retain parsed frames, never file padding."""

    class Input:
        line = b""

        def readline(self, size):
            if stop.is_set():
                raise ValueError("replay_cancelled")
            self.line = stream.readline(size)
            return self.line

    rows = []
    with Path(path).open("rb") as stream:
        captured = Input()
        for _ in replay(captured):
            # The frozen core has validated this exact line before yielding.
            rows.append(json.loads(captured.line))
    if not rows:
        raise ValueError("empty_replay")
    return rows


def _worker(
    profile, channel, stop, group, decoder_lock, descendant, ros_grant=None, ros_control=None
):
    own_descendants(group)
    source = None
    inference_count = 0
    try:
        if profile.driver == "sensor-ros":
            from .sensors.ros_worker import ros_worker

            ros_worker(
                profile, ros_grant, lambda message: _latest(channel, message), stop, ros_control
            )
            return
        if profile.driver == "sensor-replay":
            from .sensors.worker import replay_worker

            replay_worker(profile, lambda message: _latest(channel, message), stop)
            return
        if profile.driver == "replay":
            rows = _load_replay_rows(profile.address, stop)
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
        source = {"file": FileSource, "uvc": UVCSource, "rtsp": RTSPSource}[profile.driver](
            decoder_lock=decoder_lock, descendant=descendant
        )
        source.open(
            SourceConfig(profile.driver, profile.address, profile.backend, profile.calibration_id)
        )
        previous = None
        while not stop.is_set():
            frame = source.read(time.monotonic_ns() + 2_000_000_000)
            if isinstance(frame, SourceFault):
                _latest(
                    channel,
                    {
                        "data": None,
                        "reason": "source_lost",
                        "latency_ms": 0,
                        "inference_count": inference_count,
                        "capture_drops": source.drops,
                    },
                )
                return
            pixels = np.frombuffer(frame.pixels, dtype=np.uint8).reshape(
                frame.height, frame.width, 3
            )
            if frame.width > 1280 or frame.height > 720:
                # Pinned detector requires <=1280x720; no implicit resize/calibration change.
                raise ValueError()
            proposals = detector.infer(pixels, lighting=profile.lighting)
            inference_count += 1
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
                    "inference_count": inference_count,
                    "registration_valid": bool(ego and ego["valid"]),
                    "capture_drops": source.drops,
                },
            )
    except Exception:
        _latest(channel, {"data": None, "reason": "model_error", "latency_ms": 0})
    finally:
        if source:
            source.close()


class RuntimePipeline:
    def __init__(self, profile: Profile, *, worker=_worker, ros_grant=None, ros_guard=None):
        self.worker = worker
        self.profile = profile
        self.ros_grant = ros_grant
        self.ros_guard = ros_guard
        if profile.driver == "sensor-ros" and ros_guard is None:
            from .sensors.ros_authority import ClockGuard, issue_boot_grant, read_ros_manifest

            manifest = read_ros_manifest(profile)
            if self.ros_grant is None:
                self.ros_grant = issue_boot_grant(manifest)
            self.ros_guard = ClockGuard(self.ros_grant, manifest, boot_id=self.ros_grant.boot_id)
        self.core = self._new_core()
        self.process = None
        self.reason = "source_lost"
        self.processed = 0
        self.last_latency_ms = 0.0
        self.proposal_count = 0
        self.inferences = 0
        self.worker_inferences = 0
        self.capture_drops = 0
        self.prior_drops = {
            "capture_sequence_gaps": 0,
            "mailbox_overwritten": 0,
            "mailbox_rejected": 0,
        }
        self.last_message_ns = 0
        self.last_result = None
        self.sensor_batches = 0
        self.worker_sensor_batches = 0
        self.sensor_state = "idle"
        self.sensor_expires_ns = 0
        self.sensor_emitted_ns = 0

    def _new_core(self):
        core = Session()
        now = time.monotonic_ns() // 1_000_000
        empty = {
            "version": 3,
            "at_ms": now,
            "lighting": self.profile.lighting,
            "evidence": "external_unverified",
            "mode": "direct",
            "contract": self.profile.contract,
            "scene_break": True,
            "sensors": [],
            "ego": {"dx": 0, "dy": 0, "variance": 0.05, "valid": False},
        }
        core.step(json.dumps(empty).encode(), now_ms=now)
        return core

    def start(self):
        self.stop_worker()
        self.core.close()
        self.core = self._new_core()
        ctx = mp.get_context("spawn")
        self.channel = Mailbox(ctx)
        self.ros_control = Mailbox(ctx) if self.profile.driver == "sensor-ros" else None
        self.stop = StopToken(ctx)
        self.group = ctx.RawValue("q", 0)
        self.descendant = ctx.RawValue("q", 0)
        # Parent owns the decoder semaphore so abrupt worker death cannot orphan
        # its named OS resource until the whole service exits.
        self.decoder_lock = ctx.Lock() if self.profile.driver in {"file", "uvc", "rtsp"} else None
        self.process = ctx.Process(
            target=self.worker,
            args=(
                self.profile,
                self.channel,
                self.stop,
                self.group,
                self.decoder_lock,
                self.descendant,
            )
            + ((self.ros_grant, self.ros_control) if self.profile.driver == "sensor-ros" else ()),
        )
        self.process.start()
        self.started_ns = time.monotonic_ns()
        self.last_message_ns = self.started_ns
        self.worker_inferences = 0
        self.worker_sensor_batches = 0

    def tick(self, now_ns):
        if self.process is None:
            return self.snapshot(now_ns)
        if self.ros_guard is not None and not self.ros_guard.check():
            self._revoke_ros()
            return self.snapshot(now_ns)
        try:
            message = self.channel.get_nowait()
        except (queue.Empty, AttributeError):
            return self.snapshot(now_ns)
        if self.ros_guard is not None:
            if message.get("sensor_state") == "fault":
                self._revoke_ros(message.get("sensor_fault"))
                return self.snapshot(now_ns)
            if message.get("sensor_generation") != self.ros_grant.generation:
                return self.snapshot(now_ns)
        if self.profile.driver in {"sensor-replay", "sensor-ros"}:
            observed_batches = message.get("sensor_batches", self.worker_sensor_batches)
            self.sensor_batches += max(0, observed_batches - self.worker_sensor_batches)
            self.worker_sensor_batches = observed_batches
            self.sensor_state = message.get("sensor_state", "fault")
            self.sensor_expires_ns = message.get("sensor_expires_ns", 0)
            self.sensor_emitted_ns = message.get("sensor_emitted_ns", 0)
            self._renew_ros(now_ns)
        self.processed += 1
        self.last_message_ns = now_ns
        self.reason = message["reason"]
        self.last_latency_ms = message["latency_ms"]
        if message["data"] is not None:
            self.last_latency_ms = max(0, now_ns / 1e6 - json.loads(message["data"])["at_ms"])
        self.proposal_count = message.get("proposal_count", 0)
        self.capture_drops = max(self.capture_drops, message.get("capture_drops", 0))
        observed = message.get("inference_count", self.worker_inferences)
        self.inferences += max(0, observed - self.worker_inferences)
        self.worker_inferences = observed
        if message["data"] is not None:
            self.last_result = self.core.step(message["data"], now_ms=now_ns // 1_000_000)
            return copy.deepcopy(self.last_result)
        self.last_result = None
        return self.snapshot(now_ns)

    def _revoke_ros(self, reason="renewal_rejected"):
        self.ros_guard.close(reason=reason)
        self.sensor_state = "fault"
        self.sensor_expires_ns = 0
        self.last_result = None
        _latest(self.ros_control, {"revoke": True})

    def _renew_ros(self, now_ns):
        guard = self.ros_guard
        if (
            guard is None
            or guard.manifest.renewal == "disabled"
            or now_ns < self.ros_grant.issued_ns + guard.manifest.valid_for_ns // 2
            or not self.sensor_status(now_ns)["available"]
        ):
            return
        from .sensors.ros_authority import read_ros_manifest

        try:
            grant = guard.renew(
                read_ros_manifest(self.profile),
                emitted_ns=self.sensor_emitted_ns,
                expires_ns=self.sensor_expires_ns,
            )
            self.ros_grant = grant
            self.sensor_state = "waiting"
            self.sensor_expires_ns = 0
            self.last_result = None
            # Only parent writes this bounded mailbox. If busy, fail closed rather
            # than advance authority without a worker transition.
            self.ros_control.put_nowait({"grant": asdict(grant)})
        except (ValueError, OSError, queue.Full):
            self._revoke_ros()

    def snapshot(self, now_ns):
        now = now_ns // 1_000_000
        result = self.last_result
        if (
            result is not None
            and result["state"] == "PRESENT"
            and 0 <= now - result["at_ms"] <= 100
            and all(t["expires_at_ms"] >= now for t in result["tracks"] if t["status"] == "PRESENT")
        ):
            return copy.deepcopy(result)
        self.last_result = self.core.watchdog(now_ms=now)
        return copy.deepcopy(self.last_result)

    def sensor_status(self, now_ns):
        available = (
            self.sensor_state == "processing"
            and 0 <= now_ns - self.sensor_emitted_ns <= 100_000_000
            and now_ns <= self.sensor_expires_ns
            and self.process is not None
            and (self.ros_grant is None or now_ns <= self.ros_grant.valid_until_ns)
            and (self.ros_guard is None or not self.ros_guard.closed)
        )
        return {
            "state": "stale"
            if self.sensor_state == "processing" and not available
            else self.sensor_state,
            "batches": self.sensor_batches,
            "available": available,
            "source_evidence": "external_unverified"
            if self.profile.driver == "sensor-ros"
            else "recorded",
            "qualified": False,
            **(
                {
                    "authority_generation": self.ros_grant.generation,
                    "authority_fault": self.ros_guard.fault,
                }
                if self.ros_grant
                else {}
            ),
        }

    def drop_counts(self):
        channel = getattr(self, "channel", None)
        return {
            "capture_sequence_gaps": self.prior_drops["capture_sequence_gaps"] + self.capture_drops,
            "mailbox_overwritten": self.prior_drops["mailbox_overwritten"]
            + (channel.overwritten.value if channel else 0),
            "mailbox_rejected": self.prior_drops["mailbox_rejected"]
            + (channel.rejected.value if channel else 0),
        }

    def stop_worker(self):
        self.last_result = None
        self.sensor_expires_ns = 0
        self.sensor_state = "fault" if self.ros_guard and self.ros_guard.closed else "idle"
        if self.process is not None:
            self.stop.set()
            self.process.join(timeout=1)
            if os.name == "posix" and self.group.value == self.process.pid:
                # Only the group created by this worker; descendants share it.
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(self.group.value, sig)
                    except (ProcessLookupError, PermissionError):
                        break
                # Some sandboxes disallow group signals. The source registers its
                # one direct decoder child in parent-owned memory as a fallback.
                if self.descendant.value > 0:
                    try:
                        os.kill(self.descendant.value, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.descendant.value = 0
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=1)
            self.process.close()
            self.process = None

    def close(self):
        self.stop_worker()
        self.core.close()
