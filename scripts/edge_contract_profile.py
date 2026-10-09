#!/usr/bin/env python3
"""Compare typed models with schema interpretation on bounded API output workloads.

Diagnostic CPU/allocation measurements, not latency or appliance qualification.
Run with the edge package and hash-locked server test dependencies installed.
"""

import argparse
import copy
import hashlib
import importlib.metadata
import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Annotated, Literal

from aethron_edge.contracts import ReplayReport
from aethron_edge.openapi import document
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def measure(validate, body):
    validate(body)
    cpu, wall = [], []
    for _ in range(3):
        start_cpu, start_wall = time.process_time_ns(), time.perf_counter_ns()
        validate(body)
        cpu.append((time.process_time_ns() - start_cpu) / 1e6)
        wall.append((time.perf_counter_ns() - start_wall) / 1e6)
    tracemalloc.start()
    validate(body)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "cpu_median_ms": statistics.median(cpu),
        "wall_median_ms": statistics.median(wall),
        "python_traced_peak_bytes": peak,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maximum", action="store_true", help="also measure the 300x32 shape bound"
    )
    parser.add_argument(
        "--msgspec-probe", action="store_true", help="requires isolated msgspec 0.22.0"
    )
    args = parser.parse_args()
    results = json.loads((ROOT / "contracts/fixtures/v3/blackout-output.json").read_text())[
        "results"
    ]
    normal = {
        "api_version": "1",
        "runtime_mode": "replay",
        "frame_count": len(results),
        "results": results,
    }
    snapshot = copy.deepcopy(next(frame for frame in results if frame["tracks"]))
    snapshot["tracks"] = [copy.deepcopy(snapshot["tracks"][0]) for _ in range(32)]
    maximum = dict(normal, frame_count=300, results=[copy.deepcopy(snapshot) for _ in range(300)])
    spec = document()
    schema = {**spec["components"]["schemas"]["ReplayReport"], "components": spec["components"]}
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    measurements = {}
    workloads = [("frozen_24", normal)]
    if args.maximum:
        workloads.append(("synthetic_300x32_shape", maximum))
    for name, body in workloads:
        # The maximum workload exercises shape/resource bounds, not temporal truth.
        if ReplayReport.model_validate(body).model_dump(by_alias=True) != body:
            raise RuntimeError("contract_roundtrip_changed")
        measurements[name] = {
            "sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
            "pydantic": measure(ReplayReport.model_validate, body),
            "jsonschema": measure(validator.validate, body),
        }
    decimal_count = dict(normal, frame_count=float(normal["frame_count"]))
    try:
        ReplayReport.model_validate(decimal_count)
        typed_rejects_decimal_count = False
    except ValueError:
        typed_rejects_decimal_count = True
    output = {
        "qualified": False,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("pydantic", "pydantic_core", "jsonschema")
        },
        "results": measurements,
        "integer_token_constraint": {
            "typed_rejects_decimal_count": typed_rejects_decimal_count,
            "schema_accepts_decimal_count": validator.is_valid(decimal_count),
        },
        "source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "integrations/edge/aethron_edge/contracts.py",
                "integrations/edge/aethron_edge/common_types.py",
                "integrations/edge/aethron_edge/openapi.py",
                "scripts/edge_contract_profile.py",
                "contracts/openapi/aethron-edge-v1.json",
            )
        },
    }
    if args.msgspec_probe:
        import msgspec

        if msgspec.__version__ != "0.22.0":
            raise RuntimeError("probe_requires_msgspec_0_22_0")

        class Candidate(msgspec.Struct, forbid_unknown_fields=True):
            centre: Annotated[
                list[Annotated[float, msgspec.Meta(ge=0, le=1)]],
                msgspec.Meta(min_length=2, max_length=2),
            ]
            horizon_ms: Literal[200]
            evidence: Literal[False]

        invalid = {"centre": [0.5, 0.5], "horizon_ms": 200, "evidence": 0}
        try:
            msgspec.convert(invalid, type=Candidate, strict=True)
            convert_rejects = False
        except msgspec.ValidationError:
            convert_rejects = True
        constructed = Candidate(**invalid)
        output["msgspec_probe"] = {
            "version": msgspec.__version__,
            "strict_convert_rejects_numeric_false": convert_rejects,
            "constructor_accepts_numeric_false": type(constructed.evidence) is int,
            "schema": msgspec.json.schema(Candidate),
            "scope": "representative constant/constructor boundary; not a full migration benchmark",
        }
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
