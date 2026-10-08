import json
import unittest
from pathlib import Path

from aethron_edge.contracts import ReplayReport, SceneEnvelope
from aethron_edge.protocol import replay_bytes

FIXTURE = Path(__file__).resolve().parents[2] / "examples/temporal-blackout.jsonl"


class StrictContract(unittest.TestCase):
    def test_frozen_replay_and_closed_report(self):
        report = replay_bytes(FIXTURE.read_bytes())
        self.assertIsInstance(report, ReplayReport)
        self.assertEqual(report.frame_count, 24)
        self.assertEqual(report.results[-1].tracks[0].sources, ["depth", "lwir", "radar"])
        body = report.model_dump(by_alias=True)
        body["now_ms"] = 123
        with self.assertRaises(ValueError):
            ReplayReport.model_validate(body)

    def test_reject_raw_invalid_input_without_echo(self):
        line = FIXTURE.read_bytes().splitlines()[0]
        obj = json.loads(line)
        variants = [
            b" " * 65537,
            b"[" * 9 + b"0" + b"]" * 9,
            line.replace(b'"at_ms":', b'"at_ms":0,"at_ms":', 1),
            line.replace(b'"version":3', b'"version":NaN'),
            line * 301,
        ]
        for change in (
            {"unknown": "private-sentinel"},
            {"at_ms": True},
            {"evidence": "external_unverified"},
        ):
            variants.append(json.dumps(dict(obj, **change)).encode())
        score = json.loads(line)
        score["sensors"][0]["detections"][0]["score"] = True
        variants.append(json.dumps(score).encode())
        for data in variants:
            with self.subTest(length=len(data)), self.assertRaises(ValueError) as ctx:
                replay_bytes(data)
            self.assertNotIn("private-sentinel", str(ctx.exception))

    def test_reject_frame_count_and_duration_boundary(self):
        obj = json.loads(FIXTURE.read_bytes().splitlines()[0])
        for count, step in [(301, 1), (2, 30000)]:
            rows = []
            for n in range(count):
                obj["at_ms"] = n * step
                rows.append(json.dumps(obj).encode())
            with self.assertRaises(ValueError):
                replay_bytes(b"\n".join(rows))

    def test_scene_does_not_accept_unknown_state_or_boolean_clock(self):
        report = replay_bytes(FIXTURE.read_bytes())
        envelope = {
            "api_version": "1",
            "kind": "scene",
            "sequence": 1,
            "session": "a" * 32,
            "clock": {"domain": "edge_monotonic", "emitted_ms": 0, "valid_for_ms": 0},
            "result": report.results[0].model_dump(by_alias=True),
        }
        SceneEnvelope.model_validate(envelope)
        envelope["clock"]["emitted_ms"] = True
        with self.assertRaises(ValueError):
            SceneEnvelope.model_validate(envelope)
        envelope["clock"]["emitted_ms"] = 0
        envelope["result"]["state"] = "SAFE"
        with self.assertRaises(ValueError):
            SceneEnvelope.model_validate(envelope)
