"""Actual local RTSP/RTP decode; server and publisher are test infrastructure only."""

import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from aethron_edge.sources.base import SourceConfig, SourceFault
from aethron_edge.sources.rtsp import RTSPSource

ROOT = Path(__file__).resolve().parents[2]


class RTSPIntegration(unittest.TestCase):
    def test_local_rtsp_pixels_and_disconnect(self):
        import imageio_ffmpeg

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "mediamtx.yml"
            config.write_text(
                f"logLevel: error\nrtspAddress: 127.0.0.1:{port}\nrtspTransports: [tcp]\nrtmp: no\nhls: no\nwebrtc: no\nsrt: no\npaths:\n  fixture:\n"
            )
            log = (ROOT / "build/ecosystem-phase1/rtsp-tools.log").open("w")
            server = subprocess.Popen(
                [str(ROOT / "build/ecosystem-phase1/tools/mediamtx"), str(config)],
                stdout=log,
                stderr=log,
            )
            publisher = None
            source = RTSPSource()
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                url = f"rtsp://127.0.0.1:{port}/fixture"
                publisher = subprocess.Popen(
                    [
                        imageio_ffmpeg.get_ffmpeg_exe(),
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-re",
                        "-loop",
                        "1",
                        "-i",
                        str(ROOT / "data/rgb-smoke/person.png"),
                        "-vf",
                        "scale=320:240",
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
                    stdout=log,
                    stderr=log,
                )
                time.sleep(1)
                source.open(SourceConfig("rtsp", url, "ffmpeg", "test"))
                frame = source.read(time.monotonic_ns() + 10_000_000_000)
                self.assertNotIsInstance(frame, SourceFault)
                self.assertEqual((frame.width, frame.height), (320, 240))
                self.assertIsNone(frame.capture_ns)
                publisher.terminate()
                publisher.wait(timeout=5)
                server.terminate()
                server.wait(timeout=5)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    result = source.read(time.monotonic_ns() + 500_000_000)
                    if isinstance(result, SourceFault):
                        break
                    self.assertIsNone(result.capture_ns)
                self.assertIsInstance(result, SourceFault)
            finally:
                source.close()
                for process in (publisher, server):
                    if process and process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
                log.close()
