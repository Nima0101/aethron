"""Local live/source RGB inference for UVC, camera-index, video or explicit RTSP.

Observation-only research interface. It never commands a vehicle or drone.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def source_value(value):
    """Use numeric device indexes, file paths or user-supplied transport URLs."""
    return int(value) if value.isdecimal() else value


def run(source, backend, max_frames=0):
    import cv2

    from aethron.vision.yolox import MODEL_SHA256, RGBDetector

    capture = cv2.VideoCapture(source_value(source))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError("camera_or_stream_unavailable")
    detector = RGBDetector(ROOT / "build/models/yolox.onnx", backend=backend)
    index = 0
    try:
        while max_frames == 0 or index < max_frames:
            # Frame acquisition can be arbitrarily stale on buffered network feeds.
            grabbed_at = time.monotonic()
            success, image = capture.read()
            if not success:
                break
            if image is None or image.ndim != 3:
                raise RuntimeError("invalid_camera_frame")
            h, w = image.shape[:2]
            if h > 720 or w > 1280:
                scale = min(1280 / w, 720 / h)
                image = cv2.resize(image, (int(w * scale), int(h * scale)))
                h, w = image.shape[:2]
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            model_start = time.monotonic()
            observations = detector.infer(rgb, lighting="daylight")
            inference_ms = (time.monotonic() - model_start) * 1000
            elapsed_ms = (time.monotonic() - grabbed_at) * 1000
            response = {
                "kind": "aethron_video_observation_v1",
                "frame": index,
                "source": "camera_or_recorded_video",
                "model_sha256": MODEL_SHA256,
                "backend": backend,
                "image_size": [w, h],
                "observations": observations,
                "inference_ms": round(inference_ms, 3),
                "elapsed_since_read_started_ms": round(elapsed_ms, 3),
                "capture_transport_age": "unknown",
                "safety_state": "UNKNOWN",
                "operational_action": None,
                "freshness": "unqualified",
                "note": "Observation only, no camera/clock calibration or controller authority",
            }
            print(json.dumps(response, separators=(",", ":")), flush=True)
            index += 1
    finally:
        capture.release()
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="0",
        help="Camera device index (0), local video file or explicit RTSP URL.",
    )
    parser.add_argument("--backend", choices=("opencv", "coreml"), default="opencv")
    parser.add_argument("--max-frames", type=int, default=0)
    args = parser.parse_args()
    if args.max_frames < 0:
        parser.error("--max-frames must be >=0")
    try:
        processed = run(args.source, args.backend, args.max_frames)
        if processed == 0:
            raise RuntimeError("no_video_frames_received")
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print(json.dumps({"state": "UNKNOWN", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
