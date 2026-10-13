"""File decoding must not turn protocol URLs or playlists into network capture."""

import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from aethron_edge.sources.base import MAX_RAW, SourceConfig, _decode


class StopAfterFrame(threading.Event):
    def wait(self, timeout=None):
        self.set()
        return True


class FileDecoderProtocols(unittest.TestCase):
    def decode(self, address):
        slot, metadata = bytearray(MAX_RAW), [0, 0, 0, 0]
        # Exercise native decoding, with only diagnostic suppression kept out of
        # this test process. Production uses an isolated, single-source child.
        with patch("os.dup2"):
            _decode(
                SourceConfig("file", address, "ffmpeg", "bench"),
                slot,
                metadata,
                threading.Lock(),
                StopAfterFrame(),
            )
        return metadata, slot

    def test_file_urls_and_nested_playlist_cannot_contact_network(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_error(404)

            def log_message(self, *args):
                pass

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/segment.ts"
                with tempfile.TemporaryDirectory() as directory:
                    playlist = Path(directory) / "recording.m3u8"
                    playlist.write_text(
                        "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:1\n"
                        f"#EXTINF:1,\n{url}\n#EXT-X-ENDLIST\n"
                    )
                    for address in (url, str(playlist)):
                        with (
                            self.subTest(address=address),
                            patch.dict(
                                os.environ,
                                {
                                    "OPENCV_FFMPEG_CAPTURE_OPTIONS": "protocol_whitelist;file,http,tcp"
                                },
                            ),
                        ):
                            requests.clear()
                            metadata, _ = self.decode(address)
                            self.assertEqual(requests, [])
                            self.assertEqual(metadata[0], -2)
            finally:
                server.shutdown()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_local_file_still_decodes_with_inherited_options_restricted(self):
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.avi"
            # Exact RGB bytes require a lossless fixture; MJPEG rounds colors.
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 20, (64, 48))
            self.assertTrue(writer.isOpened())
            writer.write(np.full((48, 64, 3), (17, 83, 211), dtype=np.uint8))
            writer.release()
            with patch.dict(
                os.environ, {"OPENCV_FFMPEG_CAPTURE_OPTIONS": "protocol_whitelist;http,tcp"}
            ):
                metadata, slot = self.decode(str(path))
            self.assertEqual(metadata[:3], [1, 64, 48])
            self.assertEqual(bytes(slot[: 64 * 48 * 3]), bytes([211, 83, 17]) * (64 * 48))
