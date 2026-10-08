"""Installed real file/RTSP -> pinned detector -> local API -> Python consumer.

Capture exposure is unqualified: successful decoding is never promoted to a
current detection. This checks actual source execution with aggregate counters.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run():
    import cv2
    import imageio_ffmpeg

    area = ROOT / "build/ecosystem-phase1"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    output = []
    with tempfile.TemporaryDirectory(prefix="installed-pixels-") as temporary:
        work = Path(temporary)
        subprocess.run([sys.executable, "-m", "venv", str(work / "venv")], check=True)
        python = work / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(area / "wheelhouse"),
                "--require-hashes",
                "-r",
                str(ROOT / "integrations/edge/requirements-server.lock"),
                "-r",
                str(ROOT / "integrations/edge/requirements-vision.lock"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            env=env,
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(area / "package/a"),
                "aethron-edge==0.1.0",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            env=env,
        )
        shutil.copyfile(ROOT / "examples/clients/observe.py", work / "observe.py")
        token = work / "token"
        token.write_text("d" * 64)
        token.chmod(0o600)
        image = cv2.resize(cv2.imread(str(ROOT / "data/rgb-smoke/person.png")), (320, 240))
        video = work / "fixture.avi"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 240))
        if not writer.isOpened():
            raise RuntimeError("test_encoder_unavailable")
        for _ in range(100):
            writer.write(image)
        writer.release()
        for driver in ("file", "rtsp"):
            processes = []
            api_port, rtsp_port = port(), port()
            url = f"rtsp://127.0.0.1:{rtsp_port}/fixture"
            with (area / ("installed-" + driver + ".log")).open("w") as log:
                try:
                    if driver == "rtsp":
                        (work / "rtsp.yml").write_text(
                            f"logLevel: error\nrtspAddress: 127.0.0.1:{rtsp_port}\nrtspTransports: [tcp]\n"
                            "rtmp: no\nhls: no\nwebrtc: no\nsrt: no\npaths:\n  fixture:\n"
                        )
                        tool = area / "tools" / ("mediamtx.exe" if os.name == "nt" else "mediamtx")
                        processes.append(
                            subprocess.Popen(
                                [str(tool), str(work / "rtsp.yml")],
                                cwd=work,
                                stdout=log,
                                stderr=log,
                            )
                        )
                        time.sleep(1)
                        processes.append(
                            subprocess.Popen(
                                [
                                    imageio_ffmpeg.get_ffmpeg_exe(),
                                    "-hide_banner",
                                    "-loglevel",
                                    "error",
                                    "-re",
                                    "-stream_loop",
                                    "-1",
                                    "-i",
                                    str(video),
                                    "-c:v",
                                    "libx264",
                                    "-g",
                                    "10",
                                    "-preset",
                                    "ultrafast",
                                    "-tune",
                                    "zerolatency",
                                    "-pix_fmt",
                                    "yuv420p",
                                    "-f",
                                    "rtsp",
                                    "-rtsp_transport",
                                    "tcp",
                                    url,
                                ],
                                cwd=work,
                                stdout=log,
                                stderr=log,
                            )
                        )
                        time.sleep(1)
                    config = {
                        "version": 1,
                        "runtime_mode": "interactive",
                        "port": api_port,
                        "profiles": [
                            {
                                "name": "pixels",
                                "driver": driver,
                                "address": str(video) if driver == "file" else url,
                                "model": str(ROOT / "build/models/yolox.onnx"),
                            }
                        ],
                        "credentials": [
                            {
                                "token_file": str(token),
                                "principal": {
                                    "name": "consumer",
                                    "scopes": ["observe", "session:manage"],
                                },
                            }
                        ],
                        "status_file": str(work / "status.json"),
                    }
                    (work / "status.json").unlink(missing_ok=True)
                    (work / "config.json").write_text(json.dumps(config))
                    processes.append(
                        subprocess.Popen(
                            [
                                str(python),
                                "-I",
                                "-m",
                                "aethron_edge",
                                "serve",
                                "--config",
                                str(work / "config.json"),
                            ],
                            cwd=work,
                            env=env,
                            stdout=log,
                            stderr=log,
                        )
                    )
                    started = time.monotonic()
                    deadline = started + 150  # functional startup; never a freshness allowance
                    while time.monotonic() < deadline:
                        try:
                            status = json.loads((work / "status.json").read_text())
                            if status["inferences"] > 0:
                                break
                        except (OSError, ValueError):
                            pass
                        time.sleep(0.1)
                    else:
                        raise AssertionError(driver + ": no installed real pixel inference")
                    base = f"http://127.0.0.1:{api_port}"
                    consumer = subprocess.run(
                        [
                            str(python),
                            "-I",
                            str(work / "observe.py"),
                            "--url",
                            base,
                            "--token-file",
                            str(token),
                            "--profile",
                            "pixels",
                            "--limit",
                            "3",
                        ],
                        cwd=work,
                        env=env,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    events = [json.loads(line) for line in consumer.stdout.splitlines()]
                    assert len(events) == 3 and all(e["current_state"] == "UNKNOWN" for e in events)
                    with httpx.Client(
                        base_url=base, headers={"Authorization": "Bearer " + token.read_text()}
                    ) as client:
                        capability = client.get("/api/v1/capabilities").json()
                        assert (
                            capability["drivers"] == [driver] and capability["provider"] == "opencv"
                        )
                    output.append(
                        {
                            "driver": driver,
                            "installed": True,
                            "inferences": status["inferences"],
                            "events": len(events),
                            "current_state": "UNKNOWN",
                            "time_to_observed_inference_s": time.monotonic() - started,
                            "exposure_clock_qualified": False,
                            "hardware_qualified": False,
                        }
                    )
                finally:
                    for process in reversed(processes):
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=15)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=5)
    (area / "installed-pixels.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output))


if __name__ == "__main__":
    run()
