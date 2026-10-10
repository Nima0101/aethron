"""Offline P16 consumption of P3 diagnostics; never ROS/DDS qualification."""

import hashlib
import json
import unittest
from pathlib import Path

from aethron_edge.sensors import ros2

from aethron.passport_evidence import verify_evidence

ROOT = Path(__file__).resolve().parents[2]


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


class RosStatusConformance(unittest.TestCase):
    def vectors(self):
        path = ROOT / "examples/interop/ros-status-vectors-v1.json"
        self.assertTrue(path.is_file(), "missing published ROS status conformance corpus")
        return json.loads(path.read_bytes())

    def bind(self, case, blob=None):
        result = verify_evidence(
            case["envelope"].encode(),
            case["policy"].encode(),
            (case["evidence"].encode() if blob is None else blob,),
            **case["arguments"],
        )
        self.assertIs(result.motion_authority, False)
        self.assertIs(result.evidence_verified, False)
        return result

    def test_published_source_and_case_inventory(self):
        vectors = self.vectors()
        self.assertEqual(vectors["source_commit"], "a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46")
        self.assertEqual(
            [c["name"] for c in vectors["cases"]], ["idle", "receiving", "lost", "invalid"]
        )
        self.assertEqual(
            Path(ros2.__file__).resolve(), ROOT / "integrations/edge/aethron_edge/sensors/ros2.py"
        )
        self.assertEqual(
            vectors["source_sha256"],
            {
                "integrations/edge/aethron_edge/__init__.py": "fc3adf2bb0f73d7339bc54e6d0fb2f94c5dc53a2946bac32856cf5f01b61faa9",
                "integrations/edge/aethron_edge/mailbox.py": "84b6c32191d1cd21f5469c908be50b38179d6d594cc9fd1865e2b06e3851b090",
                "integrations/edge/aethron_edge/sensors/__init__.py": "98905b1b18d58ff7bcee36a3854f2022be6443c0b36c4217f4f5781197f8d92a",
                "integrations/edge/aethron_edge/sensors/geometry.py": "24dbd7e248990f426d985d05e9add08615621381f4391209a85682102f50d02b",
                "integrations/edge/aethron_edge/sensors/packets.py": "56d66f258b24f8cf4d4af9a1b1328a1bbaf326b839e5edf08f3a5327ff281192",
                "integrations/edge/aethron_edge/sensors/rectification.py": "b034b4f5b2e0c5c4bda51f5adfcb4a15193ebe7497ab4099c7887fb57c49f6db",
                "integrations/edge/aethron_edge/sensors/ros2.py": "41aece1eff1dd5e6ae77272959354c8a9bcc6465ec10da2da7b747ad97589912",
                "integrations/edge/aethron_edge/sources/__init__.py": "c68be66b7a8e4e95cafcc1cdcf108c0532d1d2a53b55def660cbfdc4b8034f48",
                "integrations/edge/aethron_edge/sources/base.py": "0617c1b46c55416ff779189c270c7f5e46cd52a7cc0eaa03328c6800b8bbc319",
            },
        )
        for path, digest in vectors["source_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_actual_status_transitions_bind_without_qualification(self):
        vectors = self.vectors()
        ingress = ros2.RosIngress(
            modality="depth", frame_id="fixture_optical", meters_per_unit=0.002
        )
        message = dict(vectors["message"], data=bytes.fromhex(vectors["data_hex"]))
        statuses = [ingress.status(now_ns=2_000_000_000)]
        observation = ingress.image(message, now_ns=2_010_000_000)
        self.assertIsNone(observation.capture_ns)
        self.assertIs(observation.live_evidence, False)
        statuses.append(ingress.status(now_ns=2_010_000_000))
        statuses.append(ingress.status(now_ns=2_110_000_001))
        fault = ingress.image(message, now_ns=2_120_000_000)
        self.assertEqual(fault.reason, "clock_discontinuity")
        self.assertEqual(ingress.take(now_ns=2_120_000_000).reason, "source_waiting")
        statuses.append(ingress.status(now_ns=2_120_000_000))
        self.assertEqual(len(vectors["cases"]), len(statuses))
        for case, status in zip(vectors["cases"], statuses, strict=True):
            with self.subTest(case=case["name"]):
                self.assertEqual(wire(status), case["evidence"].encode())
                self.assertEqual(status["state"], "UNKNOWN")
                self.assertIs(status["qualified"], False)
                result = self.bind(case, wire(status))
                self.assertEqual(result.status, "bound")
                self.assertEqual(result.reason, "content_digests_match")
                self.assertEqual(
                    [(e.kind, e.outcome) for e in result.evidence], [("synthetic", "unknown")]
                )
                # UTC verifier time is not ROS or host-monotonic diagnostic time.
                self.assertEqual(result.expires_at, 2000)
                self.assertEqual(status["clock_domain"], "host_monotonic")

    def test_status_changes_cannot_reuse_authentication(self):
        case = self.vectors()["cases"][1]
        self.assertEqual(self.bind(case).status, "bound")
        status = json.loads(case["evidence"])
        for change in (
            {"qualified": True},
            {"state": "SAFE"},
            {"expires_ns": status["expires_ns"] + 1},
        ):
            with self.subTest(change=change):
                result = self.bind(case, wire(dict(status, **change)))
                self.assertEqual(
                    (result.status, result.reason), ("rejected", "evidence_set_mismatch")
                )
                self.assertEqual(result.evidence, ())
                self.assertIsNone(result.passport_sha256)
                self.assertIsNone(result.policy_revision)
                self.assertIsNone(result.expires_at)
