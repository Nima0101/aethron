"""Fixed offline installed-package conformance; no hardware qualification."""

import json
import sys
from hashlib import sha256
from pathlib import Path

from aethron.interop_bundles import verify_task_bundle
from aethron.interop_federation import verify_federated_bundle
from aethron.interop_inbox import BoundedInbox
from aethron.interop_tasks import validate_task
from aethron.passport_evidence import verify_evidence
from aethron.passports import verify

# Reviewed fixture bytes; changes require deliberate coverage review.
CORPORA = {
    "examples/interop/inbox-vectors-v1.json": (
        "0c3cb8ce0c8c2ce10525a63158e2ca0b6970c3953b6a09c386b133b0dace5ec3",
        4,
    ),
    "examples/interop/federation-vectors-v1.json": (
        "00c8ee5d07f2dfd976a2e3ec77f6bc7cd3acca8183f338900e99f3c70b9ab0ba",
        8,
    ),
    "examples/interop/bundle-vectors-v1.json": (
        "9dc373820c2c278b18887dc35716d941ef2ab6d76b0afe119a34787a7436a460",
        7,
    ),
    "examples/interop/task-vectors-v1.json": (
        "17510988868b8fb57f2af7b8375db21ebc980bd845450f6c9cd44bfc0fa4794c",
        7,
    ),
    "examples/passports/vectors.json": (
        "cf020ffd34e4ed7983f3b4eb625ab3dd1b764fa9bda017fa80c6d627edb8bff6",
        6,
    ),
    "examples/passports/evidence-vectors.json": (
        "9ab7461a842ee783d4a1ddafa7e89fc40b7385e6f18b74b4bad7673ae7c91dfb",
        8,
    ),
}


def load_vectors(root, relative):
    raw = (root / relative).read_bytes()
    expected_digest, expected_count = CORPORA[relative]
    if sha256(raw).hexdigest() != expected_digest:
        raise ValueError("invalid_vector_coverage")
    data = json.loads(raw)
    if type(data["cases"]) is not list or len(data["cases"]) != expected_count:
        raise ValueError("invalid_vector_coverage")
    return data


def run(root):
    if sys.flags.optimize:
        raise RuntimeError("optimized_execution_not_supported")
    vectors = load_vectors(root, "examples/interop/inbox-vectors-v1.json")
    for case in vectors["cases"]:
        inbox = BoundedInbox(**case["limits"])
        for operation in case["operations"]:
            args = dict(operation["arguments"])
            if "payload_hex" in args:
                args["payload"] = bytes.fromhex(args.pop("payload_hex"))
            result = getattr(inbox, operation["method"])(**args)
            assert [result.status, result.reason, result.items, result.payload_bytes] == operation[
                "expected"
            ], case["name"]
            assert (result.payload.hex() if result.payload is not None else None) == operation[
                "payload_hex"
            ]
            assert result.motion_authority is False
    vectors = load_vectors(root, "examples/interop/federation-vectors-v1.json")
    for case in vectors["cases"]:
        result = verify_federated_bundle(
            case["federation"].encode(),
            case["task"].encode(),
            case["envelope"].encode(),
            case["policy"].encode(),
            tuple(bytes.fromhex(value) for value in case["evidence_hex"]),
            **case["arguments"],
        )
        assert (result.status, result.reason) == (case["status"], case["reason"]), case["name"]
        assert [item.outcome for item in result.evidence] == case["outcomes"]
        assert result.execution_authority is False and result.motion_authority is False
        assert result.evidence_verified is False
    vectors = load_vectors(root, "examples/interop/bundle-vectors-v1.json")
    for case in vectors["cases"]:
        result = verify_task_bundle(
            case["task"].encode(),
            case["envelope"].encode(),
            case["policy"].encode(),
            tuple(bytes.fromhex(value) for value in case["evidence_hex"]),
            **case["arguments"],
        )
        assert (result.status, result.reason) == (case["status"], case["reason"]), case["name"]
        assert [item.outcome for item in result.evidence] == case["outcomes"]
        assert result.execution_authority is False and result.motion_authority is False
    vectors = load_vectors(root, "examples/interop/task-vectors-v1.json")
    for case in vectors["cases"]:
        result = validate_task(case["task"].encode(), **case["arguments"])
        assert (result.status, result.reason) == (case["status"], case["reason"]), case["name"]
        assert result.execution_authority is False and result.motion_authority is False
    vectors = load_vectors(root, "examples/passports/vectors.json")
    for case in vectors["cases"]:
        result = verify(case["envelope"].encode(), case["policy"].encode(), **case["arguments"])
        assert (result.status, result.reason) == (case["status"], case["reason"]), case["name"]
        assert result.motion_authority is False and result.evidence_verified is False
    vectors = load_vectors(root, "examples/passports/evidence-vectors.json")
    for case in vectors["cases"]:
        blobs = tuple(bytes.fromhex(blob) for blob in case["evidence_hex"])
        result = verify_evidence(
            case["envelope"].encode(), case["policy"].encode(), blobs, **case["arguments"]
        )
        assert (result.status, result.reason) == (case["status"], case["reason"]), case["name"]
        assert [item.outcome for item in result.evidence] == case["outcomes"]
        assert result.motion_authority is False and result.evidence_verified is False
    return sum(count for _, count in CORPORA.values())


if __name__ == "__main__":
    if not sys.flags.isolated:
        raise SystemExit("run with python -I")
    count = run(Path(__file__).resolve().parents[1])
    print(json.dumps({"verified_cases": count}, sort_keys=True))
