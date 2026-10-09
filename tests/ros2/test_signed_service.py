"""Real signed appliance CLI, offline sensor worker and authenticated external clients."""

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import aethron_edge
from test_sensor_ros_appliance import fixture

import aethron


class RosSignedService(unittest.TestCase):
    def test_signed_ros_cli_zero_viewers_authenticated_sse_and_tamper_rejection(self):
        self.run_signed(raw=False)

    def test_signed_raw_depth_cli_metadata_loss_and_authenticated_sse(self):
        self.run_signed(raw=True)

    def run_signed(self, *, raw):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            bundle.mkdir()
            changes = {"version": 2}
            if raw:
                from test_ros_lens_rectification import RosLensBinding

                helper = RosLensBinding()
                helper.setup_path()
                changes = {
                    "version": 3,
                    "image_geometry": "raw_distorted",
                    "calibration": helper.fixture.config(lens=helper.lens).model_dump(),
                    "indices": [[2, 1]],
                    "topic": "/aethron/depth_raw",
                }
            config_path, _ = fixture(
                bundle, valid_for_ns=4_000_000_000, renewal="software_fixture", **changes
            )
            private, public = root / "test-only.pem", root / "test-only.pub"
            for args in (
                ["genpkey", "-algorithm", "ED25519", "-out", str(private)],
                ["pkey", "-in", str(private), "-pubout", "-out", str(public)],
            ):
                subprocess.run(["openssl", *args], check=True, capture_output=True)
            token = root / "token"
            token.write_text("a" * 64)
            token.chmod(0o600)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config = json.loads(config_path.read_text())
            config.update(
                port=port,
                status_file=str(root / "status.json"),
                integrity_bundle=".",
                trust_root=str(public),
                credentials=[
                    {
                        "token_file": str(token),
                        "principal": {"name": "test", "scopes": ["observe", "session:manage"]},
                    }
                ],
            )
            config_path.write_text(json.dumps(config))
            manifest = {
                "schema_version": 1,
                "version": 1,
                "config_version": 1,
                "files": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()
                },
            }
            (bundle / "manifest.json").write_text(json.dumps(manifest))
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-rawin",
                    "-inkey",
                    str(private),
                    "-in",
                    str(bundle / "manifest.json"),
                    "-out",
                    str(bundle / "manifest.sig"),
                ],
                check=True,
                capture_output=True,
            )
            env = dict(os.environ)
            diagnostics = env.get("AETHRON_ROS_TEST_DIAGNOSTICS") == "1"
            if env.get("PYTHONPATH"):
                # Keep the candidate ahead of a separately installed core closure,
                # which may also contain an older edge distribution.
                env["PYTHONPATH"] = os.pathsep.join(
                    dict.fromkeys(
                        [
                            str(Path(aethron_edge.__file__).resolve().parent.parent),
                            str(Path(aethron.__file__).resolve().parent.parent),
                            *(str(Path(p).resolve()) for p in env["PYTHONPATH"].split(os.pathsep)),
                        ]
                    )
                )
            if diagnostics:
                from ros_timing_probe import child_environment

                env = child_environment(root / "diagnostics", env)
            with publisher(raw=raw) as bad_metadata, (root / "server.log").open("w+") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "aethron_edge", "run", "--config", str(config_path)],
                    cwd=root,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                url = f"http://127.0.0.1:{port}"
                try:
                    deadline = time.monotonic() + 15
                    state = None
                    states = []
                    while time.monotonic() < deadline:
                        if (root / "status.json").exists():
                            state = json.loads((root / "status.json").read_text())
                            sensor = state["sensors"].get("depth", {})
                            if not states or states[-1] != sensor:
                                states.append(sensor)
                            if (
                                sensor.get("batches", 0) >= 3
                                and sensor.get("authority_generation", 0) >= 2
                                and sensor.get("available", False)
                            ):
                                break
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(log.read())
                        time.sleep(0.05)
                    if state is None:
                        log.seek(0)
                        self.fail(
                            f"no status before startup deadline; exit={process.poll()}; {log.read()}"
                        )
                    self.assertIn("depth", state["sensors"], states)
                    self.assertGreaterEqual(state["sensors"]["depth"]["batches"], 3, states)
                    self.assertGreaterEqual(
                        state["sensors"]["depth"]["authority_generation"], 2, states
                    )
                    self.assertTrue(state["sensors"]["depth"]["available"], states)
                    self.assertEqual(state["inferences"], 0)
                    if raw:
                        bad_metadata.set()
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline:
                            lost = json.loads((root / "status.json").read_text())["sensors"][
                                "depth"
                            ]
                            if not lost["available"]:
                                break
                            time.sleep(0.02)
                        self.assertFalse(lost["available"])
                        bad_metadata.clear()
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline:
                            recovered = json.loads((root / "status.json").read_text())["sensors"][
                                "depth"
                            ]
                            if recovered["available"] and recovered["batches"] > lost["batches"]:
                                break
                            time.sleep(0.02)
                        self.assertTrue(recovered["available"])
                        self.assertGreater(recovered["batches"], lost["batches"])

                    def request(route, *, data=None, method=None, authenticated=True):
                        headers = {"Authorization": "Bearer " + "a" * 64} if authenticated else {}
                        if data is not None:
                            headers["Content-Type"] = "application/json"
                            data = json.dumps(data).encode()
                        return urllib.request.urlopen(
                            urllib.request.Request(
                                url + route, data=data, method=method, headers=headers
                            ),
                            timeout=5,
                        )

                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request("/api/v1/capabilities", authenticated=False)
                    self.assertEqual(error.exception.code, 401)
                    with request("/api/v1/capabilities") as response:
                        capabilities = json.load(response)
                    self.assertEqual(capabilities["drivers"], ["sensor-ros"])
                    self.assertEqual(capabilities["provider"], "ros_geometry")
                    with request(
                        "/api/v1/sessions", data={"source_profile": "depth", "contract": "warn"}
                    ) as response:
                        handle = json.load(response)["session"]
                    with request(f"/api/v1/sessions/{handle}/events") as response:
                        self.assertEqual(response.readline(), b"event: gap\n")
                        gap = json.loads(response.readline().removeprefix(b"data: "))
                        self.assertEqual(gap["scene_state"], "UNKNOWN")
                        self.assertEqual(response.readline(), b"\n")
                        for _ in range(3):
                            self.assertEqual(response.readline(), b"event: scene\n")
                            scene = json.loads(response.readline().removeprefix(b"data: "))
                            self.assertEqual(scene["result"]["state"], "UNKNOWN")
                            self.assertEqual(scene["result"]["tracks"], [])
                            self.assertEqual(scene["clock"]["valid_for_ms"], 0)
                            self.assertNotIn("camera_xyz", json.dumps(scene))
                            self.assertEqual(response.readline(), b"\n")
                    with request(f"/api/v1/sessions/{handle}", method="DELETE") as response:
                        self.assertEqual(response.status, 204)
                    before = json.loads((root / "status.json").read_text())["sensors"]["depth"][
                        "batches"
                    ]
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        after = json.loads((root / "status.json").read_text())["sensors"]["depth"][
                            "batches"
                        ]
                        if after > before:
                            break
                        time.sleep(0.05)
                    self.assertGreater(after, before)
                    # Mutation while running must revoke at revalidation, not wait
                    # for a CLI reboot/signature check. Restoration cannot revive it.
                    sensor_path = bundle / "sensor.json"
                    original_sensor = sensor_path.read_bytes()
                    sensor_path.write_bytes(original_sensor + b"tampered")
                    deadline = time.monotonic() + 6
                    while time.monotonic() < deadline:
                        revoked = json.loads((root / "status.json").read_text())["sensors"]["depth"]
                        if revoked["state"] == "fault":
                            break
                        time.sleep(0.05)
                    self.assertEqual(revoked["state"], "fault")
                    self.assertFalse(revoked["available"])
                    sensor_path.write_bytes(original_sensor)
                    time.sleep(1.1)
                    restored = json.loads((root / "status.json").read_text())["sensors"]["depth"]
                    self.assertFalse(restored["available"])
                    self.assertEqual(restored["batches"], revoked["batches"])
                finally:
                    process.terminate()
                    process.wait(timeout=10)
                    if diagnostics:
                        from ros_timing_probe import read_rows

                        with (root / "server.log").open("rb") as captured:
                            print(
                                "AETHRON_TEST_DIAGNOSTICS "
                                + json.dumps(
                                    {"instrumented": True, "rows": read_rows(captured)},
                                    sort_keys=True,
                                ),
                                flush=True,
                            )
            for filename in ("sensor.json", "manifest.sig"):
                target = bundle / filename
                original = target.read_bytes()
                target.write_bytes(original + b"tampered")
                (root / "status.json").unlink(missing_ok=True)
                denied = subprocess.run(
                    [sys.executable, "-m", "aethron_edge", "run", "--config", str(config_path)],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(denied.returncode, 2)
                self.assertEqual(denied.stderr, b"startup_failed\n")
                self.assertFalse((root / "status.json").exists())
                target.write_bytes(original)


@contextmanager
def publisher(*, raw=False):
    """Original analytical depth input on loopback DDS; no hardware/control IO."""
    import struct
    from array import array

    from rclpy.context import Context
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import CameraInfo, Image

    context = Context()
    context.init(args=[], domain_id=73)
    node = Node(
        "aethron_signed_cli_fixture",
        context=context,
        enable_rosout=False,
        start_parameter_services=False,
    )
    qos = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )
    images = node.create_publisher(Image, "/aethron/depth_raw" if raw else "/aethron/depth", qos)
    infos = node.create_publisher(CameraInfo, "/aethron/camera_info", qos)
    info = CameraInfo()
    info.header.frame_id = "depth_optical"
    info.width = info.height = 3
    info.distortion_model = "equidistant" if raw else "plumb_bob"
    info.d = [0.0] * (4 if raw else 5)
    info.k = [2.0, 0.0, 1.0, 0.0, 2.0, 1.0, 0.0, 0.0, 1.0]
    info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    info.p = [2.0, 0.0, 1.0, 0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    if raw:
        info.p = [2.0, 0.0, 3.0, 0.0, 0.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    frame = Image()
    frame.header.frame_id = "depth_optical"
    frame.width = frame.height = 3
    frame.encoding = "16UC1"
    frame.step = 6
    frame.data = array("B", struct.pack("<9H", *([5000] * 9)))
    stop = threading.Event()
    errors = []
    bad_metadata = threading.Event()

    def work():
        try:
            while not stop.is_set():
                stamp = time.time_ns() - 5_000_000
                frame.header.stamp.sec = stamp // 1_000_000_000
                frame.header.stamp.nanosec = stamp % 1_000_000_000
                if raw:
                    info.d = [0.001 if bad_metadata.is_set() else 0.0, 0.0, 0.0, 0.0]
                infos.publish(info)
                images.publish(frame)
                stop.wait(0.02)
        except Exception as error:
            errors.append(type(error).__name__)

    thread = threading.Thread(target=work, name="aethron-test-publisher", daemon=True)
    thread.start()
    try:
        yield bad_metadata
    finally:
        stop.set()
        thread.join(timeout=2)
        node.destroy_node()
        context.shutdown()
        if thread.is_alive() or errors:
            raise RuntimeError("fixture_publisher_failed")
