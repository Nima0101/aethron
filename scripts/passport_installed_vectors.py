"""Fixed offline installed-package conformance; no hardware qualification."""

import json
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

from aethron.interop_bundles import verify_task_bundle
from aethron.interop_federation import validate_pinned_federation, verify_federated_bundle
from aethron.interop_inbox import BoundedInbox
from aethron.interop_tasks import validate_task
from aethron.passport_evidence import verify_evidence
from aethron.passport_floor_store import FederationFloorStore, FloorStoreError, PolicyFloorStore
from aethron.passports import validate_pinned_policy, verify

# Reviewed fixture bytes; changes require deliberate coverage review.
CORPORA = {
    "examples/interop/federation-policy-vectors-v1.json": (
        "74cd12782e8e418e3e2270c4a0c578a75062e6863211da0311a7b9b34ac6087d",
        10,
    ),
    "examples/passports/policy-vectors-v1.json": (
        "8014f8c76f795e15169c891a36c0b32f01f3de384d5ee6f9a9d7f1aae7b61afa",
        10,
    ),
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


def check_federation_policy(root):
    """Pinned configuration admission, including denial of every peer."""
    vectors = load_vectors(root, "examples/interop/federation-policy-vectors-v1.json")
    for case in vectors["cases"]:
        raw = case["federation"].encode()
        result = validate_pinned_federation(raw, **case["arguments"])
        assert (result.status, result.reason) == (case["status"], case["reason"]), case["name"]
        expected = (
            (sha256(raw).hexdigest(), 5, 1600)
            if case["status"] == "validated"
            else (None, None, None)
        )
        assert (result.federation_sha256, result.federation_revision, result.expires_at) == expected
        assert result.execution_authority is False
        assert result.motion_authority is False
        assert result.evidence_verified is False


def check_floor_persistence(root):
    """One synthetic real-file scenario; no power-loss or device qualification."""
    case = load_vectors(root, "examples/passports/vectors.json")["cases"][0]
    policy = case["policy"].encode()
    pin = sha256(policy).hexdigest()

    def check(row, revision, time_s, digest):
        assert (row.scope, row.policy_revision, row.minimum_time_s, row.policy_sha256) == (
            "installed-check",
            revision,
            time_s,
            digest,
        )
        assert row.execution_authority is False
        assert row.motion_authority is False
        assert row.evidence_verified is False

    with tempfile.TemporaryDirectory(prefix="aethron-floor-check-") as directory:
        path = str(Path(directory).resolve() / "floor.sqlite")
        PolicyFloorStore.create(
            path,
            scope="installed-check",
            policy=policy,
            expected_policy_sha256=pin,
            now_s=1500,
            minimum_time_s=1400,
            minimum_policy_revision=3,
        )
        store = PolicyFloorStore(path, scope="installed-check")
        check(store.read(), 3, 1500, pin)
        check(store.observe_time(now_s=1501), 3, 1501, pin)
        check(PolicyFloorStore(path, scope="installed-check").read(), 3, 1501, pin)

        updated = json.loads(policy)
        updated["revision"] = 4
        updated["revoked_keys"] = [updated["keys"][0]["key_id"]]
        raw = json.dumps(updated).encode()
        updated_pin = sha256(raw).hexdigest()
        check(
            store.accept_policy(raw, expected_policy_sha256=updated_pin, now_s=1502),
            4,
            1502,
            updated_pin,
        )
        reopened = PolicyFloorStore(path, scope="installed-check")
        check(reopened.read(), 4, 1502, updated_pin)
        for method, arguments, reason in (
            (reopened.observe_time, {"now_s": 1501}, "time_rollback"),
            (
                reopened.accept_policy,
                {"policy": policy, "expected_policy_sha256": pin, "now_s": 1503},
                "policy_rejected",
            ),
        ):
            try:
                method(**arguments)
            except FloorStoreError as error:
                assert str(error) == reason
            else:
                raise AssertionError("installed floor rollback accepted")
            check(PolicyFloorStore(path, scope="installed-check").read(), 4, 1502, updated_pin)


def check_federation_floor_persistence(root):
    """Persist deny-all and clock metadata independently of bundle success."""
    case = load_vectors(root, "examples/interop/federation-policy-vectors-v1.json")["cases"][1]
    raw = case["federation"].encode()
    pin = sha256(raw).hexdigest()
    domain = case["arguments"]["local_domain"]

    def check(row, revision, time_s, digest):
        assert (
            row.local_domain,
            row.federation_revision,
            row.minimum_time_s,
            row.federation_sha256,
        ) == (domain, revision, time_s, digest)
        assert row.execution_authority is False
        assert row.motion_authority is False
        assert row.evidence_verified is False

    with tempfile.TemporaryDirectory(prefix="aethron-federation-floor-check-") as directory:
        path = str(Path(directory).resolve() / "floor.sqlite")
        FederationFloorStore.create(path, federation=raw, **case["arguments"])
        store = FederationFloorStore(path, local_domain=domain)
        check(store.read(), 5, 1500, pin)
        check(store.observe_time(now_s=1501), 5, 1501, pin)
        check(FederationFloorStore(path, local_domain=domain).read(), 5, 1501, pin)
        changed = json.loads(raw)
        changed.update(revision=6, peers=[])
        deny_all = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode("ascii")
        deny_pin = sha256(deny_all).hexdigest()
        check(
            store.accept_federation(deny_all, expected_federation_sha256=deny_pin, now_s=1502),
            6,
            1502,
            deny_pin,
        )
        check(FederationFloorStore(path, local_domain=domain).read(), 6, 1502, deny_pin)
        for method, arguments, reason in (
            (store.observe_time, {"now_s": 1501}, "time_rollback"),
            (
                store.accept_federation,
                {"federation": raw, "expected_federation_sha256": pin, "now_s": 1503},
                "federation_rejected",
            ),
        ):
            try:
                method(**arguments)
            except FloorStoreError as error:
                assert str(error) == reason
            else:
                raise AssertionError("installed federation floor rollback accepted")
            check(FederationFloorStore(path, local_domain=domain).read(), 6, 1502, deny_pin)


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
            assert result.execution_authority is False
            assert result.evidence_verified is False
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
        assert result.evidence_verified is False
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
    vectors = load_vectors(root, "examples/passports/policy-vectors-v1.json")
    for case in vectors["cases"]:
        result = validate_pinned_policy(bytes.fromhex(case["policy_hex"]), **case["arguments"])
        expected = case["expected"]
        assert (result.status, result.reason) == (expected["status"], expected["reason"]), case[
            "name"
        ]
        assert result.policy_sha256 == expected["policy_sha256"], case["name"]
        assert result.policy_revision == expected["policy_revision"], case["name"]
        assert result.expires_at == expected["expires_at"], case["name"]
        assert result.execution_authority is False
        assert result.motion_authority is False
        assert result.evidence_verified is False
    check_federation_policy(root)
    check_floor_persistence(root)
    check_federation_floor_persistence(root)
    return sum(count for _, count in CORPORA.values()) + 2


if __name__ == "__main__":
    if not sys.flags.isolated:
        raise SystemExit("run with python -I")
    count = run(Path(__file__).resolve().parents[1])
    print(json.dumps({"verified_cases": count}, sort_keys=True))
