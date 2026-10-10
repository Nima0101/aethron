"""Offline task descriptions never grant execution or motion authority."""

import hashlib
import json
import unittest
from dataclasses import asdict
from pathlib import Path

from aethron.interop_tasks import canonicalize_task, validate_task


def document():
    return {
        "version": 1,
        "task_id": "fixture-task",
        "kind": "evidence.bind.v1",
        "subject_sha256": "a" * 64,
        "passport_sha256": "b" * 64,
        "policy_sha256": "c" * 64,
        "evidence_sha256": ["d" * 64, "e" * 64],
        "issued_at": 1000,
        "expires_at": 1300,
        "max_evidence_bytes": 1048576,
        "motion_authority": False,
    }


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def check(raw, **updates):
    arguments = {
        "expected_task_sha256": hashlib.sha256(raw).hexdigest(),
        "expected_subject_sha256": "a" * 64,
        "now_s": 1100,
        "minimum_time_s": 1000,
    }
    arguments.update(updates)
    return validate_task(raw, **arguments)


class TaskTests(unittest.TestCase):
    def test_portable_vectors(self):
        path = Path(__file__).resolve().parents[1] / "examples/interop/task-vectors-v1.json"
        for case in json.loads(path.read_bytes())["cases"]:
            result = validate_task(case["task"].encode(), **case["arguments"])
            self.assertEqual(
                (result.status, result.reason), (case["status"], case["reason"]), case["name"]
            )
            self.assertIs(result.execution_authority, False)

    def test_canonical_description_has_no_authority(self):
        raw = wire(document())
        self.assertEqual(canonicalize_task(json.dumps(document(), indent=2).encode()), raw)
        result = check(raw)
        self.assertEqual(result.status, "validated")
        self.assertEqual(result.task_sha256, hashlib.sha256(raw).hexdigest())
        for field in ("execution_authority", "motion_authority", "evidence_verified"):
            self.assertIs(asdict(result)[field], False)

    def test_exact_pin_subject_and_canonical_bytes(self):
        raw = wire(document())
        for arguments, reason in (
            ({"expected_task_sha256": "f" * 64}, "task_mismatch"),
            ({"expected_subject_sha256": "f" * 64}, "subject_mismatch"),
        ):
            self.assertEqual(check(raw, **arguments).reason, reason)
        self.assertEqual(check(json.dumps(document(), indent=2).encode()).reason, "invalid_input")

    def test_half_open_expiry_and_clock_floor(self):
        raw = wire(document())
        self.assertEqual(check(raw, now_s=1000).status, "validated")
        self.assertEqual(check(raw, now_s=1299).status, "validated")
        self.assertEqual(check(raw, now_s=1300).reason, "task_not_current")
        self.assertEqual(check(raw, now_s=999, minimum_time_s=0).reason, "task_not_current")
        self.assertEqual(check(raw, minimum_time_s=1101).reason, "time_rollback")
        for arg in ("now_s", "minimum_time_s"):
            for value in (True, 1.0, -1, 2**53, "1100"):
                self.assertEqual(check(raw, **{arg: value}).reason, "invalid_input")

    def test_closed_shapes_and_restricted_operations(self):
        for field, value in (
            ("kind", "motion.follow"),
            ("kind", "shell.exec"),
            ("motion_authority", True),
            ("motion_authority", 0),
            ("version", True),
            ("version", 1.0),
            ("task_id", "fixture\n"),
            ("person_id", "forbidden"),
            ("url", "https://invalid.example/"),
            ("expires_at", 1301),
            ("expires_at", 1000),
            ("issued_at", -1),
            ("max_evidence_bytes", 1048577),
            ("max_evidence_bytes", True),
            ("max_evidence_bytes", 0),
            ("evidence_sha256", []),
            ("evidence_sha256", ["d" * 64] * 2),
            ("evidence_sha256", ["d" * 64] * 17),
            ("passport_sha256", "B" * 64),
        ):
            changed = document()
            changed[field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual(check(wire(changed)).status, "rejected")
        for field in document():
            changed = document()
            del changed[field]
            self.assertEqual(check(wire(changed)).status, "rejected")

    def test_lexical_resource_and_type_rejection(self):
        raw = wire(document())
        for bad in (
            raw.replace(b'"version":1', b'"version":1,"version":1'),
            raw.replace(b'"version":1', b'"version":1e0'),
            b"[" * 9,
            b" " * 65537,
            b"\xff",
            b"null",
            b"[]",
        ):
            with self.assertRaises(ValueError):
                canonicalize_task(bad)
            self.assertEqual(check(bad).status, "rejected")
        for bad in (None, "{}", bytearray(raw)):
            result = validate_task(
                bad,
                expected_task_sha256="a" * 64,
                expected_subject_sha256="a" * 64,
                now_s=1100,
                minimum_time_s=1000,
            )
            self.assertEqual(result.status, "rejected")

    def test_passport_task_cannot_smuggle_evidence_budget(self):
        value = document()
        value.update(kind="passport.verify.v1", evidence_sha256=[], max_evidence_bytes=0)
        self.assertEqual(check(wire(value)).status, "validated")
        for field, extra in (("evidence_sha256", ["d" * 64]), ("max_evidence_bytes", 1)):
            changed = dict(value, **{field: extra})
            self.assertEqual(check(wire(changed)).status, "rejected")


if __name__ == "__main__":
    unittest.main()
