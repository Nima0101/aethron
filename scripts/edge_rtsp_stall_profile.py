"""Loopback-only native negotiation/cancellation comparison; no live qualification."""

import argparse
import json
import multiprocessing as mp
import os
import socket
import tempfile
import threading
import time
from pathlib import Path

from aethron_edge.mailbox import StopToken
from aethron_edge.sources.base import MAX_RAW, SourceConfig, _decode
from aethron_edge.sources.rtsp import RTSPSource


def gst_decoder(config, slot, metadata, lock, stop):
    # Probe only: never selected by the product source factory.
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    metadata[0] = -3
    import gstreamer_libs

    gstreamer_libs.setup_python_environment()
    os.environ["GST_REGISTRY_1_0"] = os.environ["GST_REGISTRY"]
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    # Scope plugin discovery to this headless probe and keep scanning inside
    # the cancellable worker; no GPU/device plugins or scanner child needed.
    os.environ["GST_PLUGIN_LOADING_WHITELIST"] = (
        "coreelements:app:rtsp:rtpmanager:playback:typefindfunctions:videoconvertscale"
    )
    os.environ["GST_REGISTRY_FORK"] = "no"
    metadata[0] = -4
    Gst.init(None)
    metadata[0] = -5
    pipeline = Gst.parse_launch(
        "rtspsrc name=source protocols=tcp tcp-timeout=3000000 latency=0 "
        "! decodebin ! videoconvert ! video/x-raw,format=RGB "
        "! appsink name=sink max-buffers=1 drop=true wait-on-eos=false sync=false"
    )
    pipeline.get_by_name("source").set_property("location", config.address)
    try:
        pipeline.set_state(Gst.State.PLAYING)
        bus = pipeline.get_bus()
        while not stop.is_set():
            if bus.timed_pop_filtered(
                50 * Gst.MSECOND, Gst.MessageType.ERROR | Gst.MessageType.EOS
            ):
                break
    finally:
        pipeline.set_state(Gst.State.NULL)


def cancellation(decoder):
    ctx = mp.get_context("spawn")
    source = RTSPSource(decoder=decoder)
    source.slot = ctx.RawArray("B", MAX_RAW)
    source.metadata = ctx.RawArray("q", 4)
    source.lock = ctx.Lock()
    source.stop = StopToken(ctx)
    connected = threading.Event()
    finish = threading.Event()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.1)

        def stall():
            while not finish.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    connected.set()
                    finish.wait(20)
                break

        thread = threading.Thread(target=stall)
        thread.start()
        config = SourceConfig(
            "rtsp", f"rtsp://127.0.0.1:{listener.getsockname()[1]}/stall", "ffmpeg", "test"
        )
        source.process = ctx.Process(
            target=decoder, args=(config, source.slot, source.metadata, source.lock, source.stop)
        )
        started = time.monotonic_ns()
        source.process.start()
        try:
            if not connected.wait(20):
                raise RuntimeError(
                    f"native_backend_did_not_connect: exit={source.process.exitcode}, metadata={list(source.metadata)}"
                )
            negotiation_ns = time.monotonic_ns() - started
            started = time.monotonic_ns()
            source.close()
            cancellation_ns = time.monotonic_ns() - started
            if cancellation_ns >= 2_000_000_000 or source.alive:
                raise RuntimeError("cancellation_bound_failed")
            return {
                "connect_ns": negotiation_ns,
                "cancel_ns": cancellation_ns,
                "worker_reaped": True,
                "slot_state": source.metadata[0],
            }
        finally:
            source.close()
            finish.set()
            thread.join(timeout=2)
            if thread.is_alive():
                raise RuntimeError("fixture_cleanup_failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("opencv", "gstreamer"), required=True)
    args = parser.parse_args()
    # A private registry makes first-use plugin discovery reproducible and keeps
    # the probe from changing a user/system GStreamer cache.
    with tempfile.TemporaryDirectory(prefix="aethron-gst-registry-") as directory:
        os.environ["GST_REGISTRY"] = str(Path(directory) / "registry.bin")
        result = cancellation(_decode if args.backend == "opencv" else gst_decoder)
    print(
        json.dumps(
            {
                "backend": args.backend,
                "scope": "stalled loopback RTSP negotiation",
                "qualified": False,
                **result,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
