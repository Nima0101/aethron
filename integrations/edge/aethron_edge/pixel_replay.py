"""Explicit bounded image replay, virtual time only; never a live capture clock."""

from pathlib import Path

from aethron.temporal.registration import estimate_translation
from aethron.vision.yolox import RGBDetector

from .calibration import CalibrationRecord
from .pipeline import build_v3
from .protocol import replay_bytes
from .sources.base import FrameEnvelope
from .timebase import MappedFrame


def replay_images(images: list[Path], model: Path):
    """Decode each supplied image once; no annotations/ground truth parameter.

    This is a bounded offline evaluation API, not the live appliance path. Its
    deliberately virtual clock and identity registration do not qualify a rig.
    """
    if not 1 <= len(images) <= 300:
        raise ValueError("replay_limit")
    import cv2
    import numpy as np

    cv2.setNumThreads(1)
    detector = RGBDetector(model, backend="opencv")
    lines = []
    previous = None
    for index, path in enumerate(images):
        with path.open("rb") as stream:
            blob = stream.read(16 * 1024 * 1024 + 1)
        if len(blob) > 16 * 1024 * 1024:
            raise ValueError("encoded_limit")
        # Pillow header probe is intentionally not required at runtime; this
        # offline local-file utility is not an untrusted upload endpoint.
        pixels = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_COLOR)
        if pixels is None:
            raise ValueError("decode_failed")
        h, w, _ = pixels.shape
        if w > 1280 or h > 720:
            raise ValueError("detector_dimensions")
        rgb = cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB)
        proposals = detector.infer(rgb, lighting="daylight")
        gray = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (160, 120))
        pgm = b"P5\n160 120\n255\n" + gray.tobytes()
        ego = estimate_translation(previous, pgm) if previous else None
        previous = pgm
        at_ns = index * 100_000_000
        frame = FrameEnvelope(
            rgb.tobytes(),
            w,
            h,
            index,
            at_ns,
            at_ns,
            "offline_virtual",
            0,
            "replay",
            evidence="recorded",
        )
        calibration = CalibrationRecord(
            "replay", w, h, 30000, "fixed", (1, 0, 0, 0, 1, 0, 0, 0, 1), 0
        )
        lines.append(
            build_v3(MappedFrame(frame, at_ns, 0), proposals, calibration, now_ns=at_ns, ego=ego)
        )
    return replay_bytes(b"\n".join(lines))
