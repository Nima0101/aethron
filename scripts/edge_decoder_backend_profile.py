"""Isolated recorded decode/RGB comparison; no physical timing qualification."""

import hashlib
import json
import multiprocessing as mp
import os
import platform
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np


def decode_worker(backend, directory, channel):
    try:
        path = directory / "fixture.avi"
        if backend == "opencv":
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "protocol_whitelist;file"
            import cv2

            cv2.setNumThreads(1)
            versions = {"opencv": cv2.__version__}
            y, x = np.indices((240, 320))
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (320, 240))
            if not writer.isOpened():
                raise RuntimeError("fixture_writer_unavailable")
            try:
                for i in range(24):
                    frame = np.stack(
                        ((x + i) % 256, (y * 2 + i) % 256, (x + y + i * 3) % 256), axis=-1
                    )
                    writer.write(frame.astype(np.uint8))
            finally:
                writer.release()

            def decode():
                cap = cv2.VideoCapture(
                    str(path),
                    cv2.CAP_FFMPEG,
                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 500],
                )
                if not cap.isOpened():
                    raise RuntimeError("opencv_fixture_open_failed")
                try:
                    while True:
                        okay, frame = cap.read()
                        if not okay:
                            break
                        yield cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).tobytes()
                finally:
                    cap.release()
        else:
            import av

            versions = {"pyav": av.__version__, "pyav_native_libraries": av.library_versions}

            def decode():
                with av.open(
                    str(path), timeout=(3, 0.5), options={"protocol_whitelist": "file"}
                ) as cap:
                    cap.streams.video[0].thread_count = 1
                    for frame in cap.decode(video=0):
                        yield frame.to_ndarray(format="rgb24").tobytes()

        samples = []
        for _ in range(5):
            frames = []
            start = time.process_time_ns()
            for frame in decode():
                if len(frame) != 320 * 240 * 3 or len(frames) >= 24:
                    raise RuntimeError("invalid_decoded_output")
                frames.append(frame)
            samples.append(time.process_time_ns() - start)
            if len(frames) != 24:
                raise RuntimeError("unexpected_frame_count")
        (directory / f"{backend}.rgb").write_bytes(b"".join(frames))
        channel.send({"cpu_ns": samples, "versions": versions})
    except Exception as error:
        channel.send({"error": type(error).__name__})
    finally:
        channel.close()


def compare(directory):
    ctx = mp.get_context("spawn")
    reports, outputs = {}, {}
    for backend in ("opencv", "pyav"):
        reader, writer = ctx.Pipe(duplex=False)
        process = ctx.Process(target=decode_worker, args=(backend, directory, writer))
        process.start()
        writer.close()
        try:
            if not reader.poll(60):
                raise RuntimeError("decoder_probe_timeout")
            reports[backend] = reader.recv()
            process.join(timeout=5)
            if process.exitcode != 0 or "error" in reports[backend]:
                raise RuntimeError("decoder_probe_failed")
        finally:
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            process.close()
            reader.close()
        outputs[backend] = (directory / f"{backend}.rgb").read_bytes()
    a, b = (np.frombuffer(outputs[name], dtype=np.uint8).astype(np.int16) for name in reports)
    return {
        "qualified": False,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "isolated_backend_processes": True,
        "reports": reports,
        "frames": 24,
        "size": [320, 240],
        "input_sha256": hashlib.sha256((directory / "fixture.avi").read_bytes()).hexdigest(),
        "output_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in outputs.items()},
        "byte_parity": outputs["opencv"] == outputs["pyav"],
        "different_channels": int(np.count_nonzero(a != b)),
        "max_channel_delta": int(np.abs(a - b).max()),
        "median_cpu_ns": {k: statistics.median(v["cpu_ns"]) for k, v in reports.items()},
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="aethron-decoder-comparison-") as directory:
        print(json.dumps(compare(Path(directory)), indent=2))
