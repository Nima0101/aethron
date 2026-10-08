"""Source ABI and cancellable, one-slot native decoder isolation."""

import multiprocessing as mp
import os
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

MAX_RAW = 1920 * 1080 * 3


@dataclass(frozen=True)
class SourceConfig:
    driver: str
    address: str
    backend: str
    calibration_id: str


@dataclass(frozen=True)
class SourceInfo:
    driver: str
    backend: str
    modality: str = "rgb"
    timestamp_origin: str = "unqualified"
    qualification_ref: str | None = None


@dataclass(frozen=True)
class SourceFault:
    reason: str
    scene_break: bool = True


@dataclass(frozen=True)
class FrameEnvelope:
    pixels: bytes = field(repr=False)
    width: int
    height: int
    sequence: int
    capture_ns: int | None
    receive_ns: int
    clock_id: str
    clock_uncertainty_ns: int
    calibration_id: str
    modality: str = "rgb"
    evidence: str = "external_unverified"


def _decode(config, slot, metadata, lock, stop):
    # Native decoder diagnostics may contain camera credentials. Suppress both
    # C-level streams in this worker; parent exposes only fixed fault codes.
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    import cv2

    cv2.setNumThreads(1)
    backends = {
        "ffmpeg": cv2.CAP_FFMPEG,
        "v4l2": cv2.CAP_V4L2,
        "avfoundation": cv2.CAP_AVFOUNDATION,
        "msmf": cv2.CAP_MSMF,
    }
    cap = None
    try:
        address = int(config.address) if config.driver == "uvc" else config.address
        cap = cv2.VideoCapture()
        parameters = (
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 500]
            if config.backend == "ffmpeg"
            else []
        )
        if not cap.open(address, backends[config.backend], parameters):
            raise ValueError()
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        width, height = (
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        if not 0 < width <= 1920 or not 0 < height <= 1080:
            raise ValueError()
        sequence = 0
        fps = cap.get(cv2.CAP_PROP_FPS)
        while not stop.is_set():
            okay, pixels = cap.read()
            if not okay:
                # Keep the final unread frame available before publishing EOF.
                while not stop.wait(0.01):
                    with lock:
                        if metadata[0] == 0:
                            metadata[0] = -1
                            return
                return
            h, w, c = pixels.shape
            if c != 3 or not 0 < w <= 1920 or not 0 < h <= 1080 or pixels.nbytes > MAX_RAW:
                raise ValueError()
            raw = cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB).tobytes()
            sequence += 1
            received = time.monotonic_ns()
            with lock:
                slot[: len(raw)] = raw
                metadata[:] = [sequence, w, h, received]
            if config.driver == "file":
                # Playback cadence is simulation time, not physical exposure.
                stop.wait(1 / max(1, min(60, fps)))
    except Exception:
        with lock:
            metadata[0] = -2
    finally:
        if cap is not None:
            cap.release()


class CaptureSource:
    driver = ""

    def __init__(self, decoder=_decode):
        self.decoder = decoder
        self.process = None
        self.config = None
        self.drops = 0
        self.last_sequence = 0

    @property
    def alive(self):
        return self.process is not None and self.process.is_alive()

    def open(self, config: SourceConfig) -> SourceInfo:
        self.close()
        if config.driver != self.driver or config.backend not in {
            "ffmpeg",
            "v4l2",
            "avfoundation",
            "msmf",
        }:
            raise ValueError("invalid_source")
        if self.driver == "rtsp":
            u = urlsplit(config.address)
            if u.scheme != "rtsp" or not u.hostname or u.fragment or config.backend != "ffmpeg":
                raise ValueError("invalid_source")
        if self.driver == "uvc" and (
            not config.address.isdecimal() or int(config.address) > 63 or config.backend == "ffmpeg"
        ):
            raise ValueError("invalid_source")
        if self.driver == "file" and config.backend != "ffmpeg":
            raise ValueError("invalid_source")
        self.config = config
        self.last_sequence = 0
        ctx = mp.get_context("spawn")
        self.slot = ctx.RawArray("B", MAX_RAW)
        self.metadata = ctx.RawArray("q", 4)
        self.lock = ctx.Lock()
        self.stop = ctx.Event()
        self.process = ctx.Process(
            target=self.decoder,
            args=(config, self.slot, self.metadata, self.lock, self.stop),
            daemon=True,
        )
        self.process.start()
        return SourceInfo(
            self.driver,
            config.backend,
            timestamp_origin="recorded_media" if self.driver == "file" else "unqualified",
        )

    def read(self, deadline_ns: int) -> FrameEnvelope | SourceFault:
        while time.monotonic_ns() < deadline_ns:
            if self.lock.acquire(timeout=0.01):
                try:
                    sequence, w, h, received = self.metadata[:]
                    if sequence < 0:
                        return SourceFault("source_lost")
                    if sequence > 0:
                        raw = bytes(self.slot[: w * h * 3])
                        self.metadata[0] = 0
                        self.drops += max(0, sequence - self.last_sequence - 1)
                        self.last_sequence = sequence
                        return FrameEnvelope(
                            raw,
                            w,
                            h,
                            sequence,
                            None,
                            received,
                            "recorded_media" if self.driver == "file" else "unqualified",
                            0,
                            self.config.calibration_id,
                            evidence="recorded" if self.driver == "file" else "external_unverified",
                        )
                finally:
                    self.lock.release()
            if not self.alive:
                return SourceFault("source_lost")
            time.sleep(0.002)
        return SourceFault("source_timeout")

    def close(self):
        if self.process is not None:
            self.stop.set()
            self.process.join(timeout=0.2)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=0.5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=0.5)
            self.process.close()
            self.process = None
