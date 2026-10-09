import json
import unittest
from pathlib import Path

from aethron_edge.openapi import document
from aethron_edge.protocol import replay_bytes
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


class OpenAPIContract(unittest.TestCase):
    def test_export_and_real_core_example_validate(self):
        spec = document()
        self.assertEqual(spec["openapi"], "3.1.1")
        schema = spec["components"]["schemas"]["ReplayReport"]
        bundle = {**schema, "components": spec["components"]}
        Draft202012Validator.check_schema(bundle)
        report = replay_bytes((ROOT / "examples/temporal-blackout.jsonl").read_bytes())
        Draft202012Validator(bundle).validate(report.model_dump(by_alias=True))
        self.assertEqual(
            spec, json.loads((ROOT / "contracts/openapi/aethron-edge-v1.json").read_text())
        )
        self.assertNotIn("/api/v1/frames", spec["paths"])
