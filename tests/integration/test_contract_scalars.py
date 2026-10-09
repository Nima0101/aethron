"""Wire constants must retain their JSON scalar type before literal validation."""

import copy
import json
import unittest
from pathlib import Path

from aethron_edge.client import Observation
from aethron_edge.contracts import Prediction, Recommendation, ReplayReport, V3Snapshot
from aethron_edge.openapi import document
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


class ContractScalars(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "contracts/fixtures/v3/blackout-output.json").read_text())
        cls.snapshot = cls.report["results"][0]

    def test_constants_reject_numeric_and_string_aliases(self):
        prediction = {"centre": [0.5, 0.5], "horizon_ms": 200, "evidence": False}
        cases = (
            (Prediction, prediction, "evidence", [0, 0.0, "false", None, True]),
            (Prediction, prediction, "horizon_ms", [200.0, "200", True, 199, None]),
            (V3Snapshot, self.snapshot, "version", [3.0, "3", True, 2, None]),
            (
                Recommendation,
                self.snapshot["recommendation"],
                "requires_independent_controller",
                [1, 1.0, "true", None, False],
            ),
        )
        for model, valid, field, invalid in cases:
            self.assertEqual(model.model_validate(valid).model_dump(by_alias=True), valid)
            for value in invalid:
                body = dict(valid, **{field: value})
                for mode in ("python", "json", "constructor"):
                    with self.subTest(model=model.__name__, field=field, value=value, mode=mode):
                        with self.assertRaises(ValueError):
                            if mode == "json":
                                model.model_validate_json(json.dumps(body))
                            elif mode == "constructor":
                                model(**body)
                            else:
                                model.model_validate(body)

    def test_nested_report_rejects_numeric_prediction_evidence(self):
        body = {
            "api_version": "1",
            "runtime_mode": "replay",
            "frame_count": len(self.report["results"]),
            "results": copy.deepcopy(self.report["results"]),
        }
        track = next(track for frame in body["results"] for track in frame["tracks"])
        track["prediction"] = {"centre": [0.5, 0.5], "horizon_ms": 200, "evidence": False}
        ReplayReport.model_validate(body)
        track["prediction"]["evidence"] = 0
        spec = document()
        schema = {**spec["components"]["schemas"]["ReplayReport"], "components": spec["components"]}
        self.assertFalse(Draft202012Validator(schema).is_valid(body))
        with self.assertRaises(ValueError):
            ReplayReport.model_validate(body)

    def test_client_erases_scene_before_rejecting_malformed_constant(self):
        scene = {
            "api_version": "1",
            "kind": "scene",
            "sequence": 1,
            "session": "a" * 32,
            "clock": {"domain": "edge_monotonic", "emitted_ms": 0, "valid_for_ms": 100},
            "result": copy.deepcopy(self.snapshot),
        }
        observer = Observation()
        observer.accept(scene, received_ns=0)
        scene["result"]["recommendation"]["requires_independent_controller"] = 1
        with self.assertRaises(ValueError):
            observer.accept(scene, received_ns=1)
        self.assertIsNone(observer.scene)
        self.assertEqual(observer.view(now_ns=1)["current_state"], "UNKNOWN")

    def test_export_preserves_scalar_types_and_constants(self):
        schemas = document()["components"]["schemas"]
        for model, field, value, kind in (
            ("Prediction", "evidence", False, "boolean"),
            ("Prediction", "horizon_ms", 200, "integer"),
            ("Recommendation", "requires_independent_controller", True, "boolean"),
            ("V3Snapshot", "version", 3, "integer"),
        ):
            prop = schemas[model]["properties"][field]
            self.assertIs(type(prop["const"]), type(value))
            self.assertEqual(prop["const"], value)
            self.assertEqual(prop["type"], kind)
