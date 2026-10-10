"""Independent structural checks; schema validity never authenticates a passport."""

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron import interop_bundles, interop_federation, interop_tasks, passports

try:
    from jsonschema import Draft202012Validator, ValidationError
    from referencing import Registry
    from referencing.exceptions import NoSuchResource, Unresolvable
except ImportError:
    Draft202012Validator = None

ROOT = Path(__file__).resolve().parents[1]


def deny_retrieval(uri):
    raise NoSuchResource(ref=uri)


def validator(name):
    schema = json.loads((ROOT / "contracts/interop" / name).read_bytes())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=Registry(retrieve=deny_retrieval))


def first_case():
    return json.loads((ROOT / "examples/passports/vectors.json").read_bytes())["cases"][0]


@unittest.skipIf(Draft202012Validator is None, "install optional passport conformance requirements")
class PassportSchemaConformance(unittest.TestCase):
    def test_runtime_comparison_detects_always_rejecting_verifier(self):
        with patch.object(
            passports,
            "verify",
            return_value=passports.VerificationResult("rejected", "crypto_unavailable"),
        ):
            with self.assertRaises(AssertionError):
                self.test_schema_success_is_not_authentication_or_time_validity()

    def test_payload_identifier_rejects_trailing_line_terminators(self):
        check = validator("passport-v1.schema.json")
        original = json.loads((ROOT / "examples/passports/vectors.json").read_bytes())[
            "canonical_payload"
        ]
        for field in ("issuer", "passport_id"):
            for suffix in ("\n", "\r", "\r\n", "\u2028", "\u2029"):
                doc = json.loads(original)
                doc[field] += suffix
                with self.subTest(field=field, suffix=repr(suffix)):
                    with self.assertRaises(ValidationError):
                        check.validate(doc)
                    with self.assertRaisesRegex(ValueError, "^invalid_passport$"):
                        passports.canonicalize(json.dumps(doc).encode())

    def test_all_schemas_are_valid_closed_and_self_contained(self):
        for name in (
            "passport-v1.schema.json",
            "passport-envelope-v1.schema.json",
            "passport-policy-v1.schema.json",
            "task-v1.schema.json",
            "federation-v1.schema.json",
            "architecture-decision-v1.schema.json",
        ):
            self.assertTrue((ROOT / "contracts/interop" / name).is_file(), name)
            schema = validator(name).schema

            def inspect(value):
                if isinstance(value, dict):
                    if "$ref" in value:
                        self.assertTrue(value["$ref"].startswith("#/"))
                    if value.get("type") == "object":
                        self.assertIs(value["additionalProperties"], False)
                        self.assertEqual(set(value["required"]), set(value["properties"]))
                    for child in value.values():
                        inspect(child)
                elif isinstance(value, list):
                    for child in value:
                        inspect(child)

            inspect(schema)
        with self.assertRaises(Unresolvable):
            Draft202012Validator(
                {"$ref": "https://invalid.example/schema"},
                registry=Registry(retrieve=deny_retrieval),
            ).validate({})

    def test_every_portable_envelope_and_policy_is_structurally_valid(self):
        outer = validator("passport-envelope-v1.schema.json")
        policy = validator("passport-policy-v1.schema.json")
        for file in ("vectors.json", "evidence-vectors.json"):
            vectors = json.loads((ROOT / "examples/passports" / file).read_bytes())
            for case in vectors["cases"]:
                with self.subTest(file=file, case=case["name"]):
                    outer.validate(json.loads(case["envelope"]))
                    policy.validate(json.loads(case["policy"]))

    def test_envelope_rejects_missing_extra_and_malformed_signature_fields(self):
        check = validator("passport-envelope-v1.schema.json")
        original = json.loads(first_case()["envelope"])
        cases = []
        for field in original:
            doc = copy.deepcopy(original)
            del doc[field]
            cases.append(doc)
        for field, value in (
            ("payloadType", "application/json"),
            ("payload", "A==="),
            ("payload", "AB=="),
            ("payload", "AAB="),
            ("payload", original["payload"] + "\n"),
            ("signatures", []),
            ("signatures", original["signatures"] * 2),
            ("extra", False),
        ):
            doc = copy.deepcopy(original)
            doc[field] = value
            cases.append(doc)
        for field, value in (
            ("sig", "A" * 85 + "B=="),
            ("sig", "A" * 84 + "=="),
            ("sig", original["signatures"][0]["sig"] + "\n"),
            ("keyid", "issuer-name"),
            ("algorithm", "none"),
        ):
            doc = copy.deepcopy(original)
            doc["signatures"][0][field] = value
            cases.append(doc)
        for doc in cases:
            with self.subTest(doc=doc):
                with self.assertRaises(ValidationError):
                    check.validate(doc)

    def test_policy_rejects_boolean_numbers_unknown_fields_and_list_overflow(self):
        check = validator("passport-policy-v1.schema.json")
        original = json.loads(first_case()["policy"])
        cases = []
        for field, value in (
            ("version", True),
            ("revision", 0),
            ("issued_at", False),
            ("expires_at", 2**53),
            ("keys", []),
            ("keys", original["keys"] * 17),
            ("revoked_passports", [str(i) for i in range(257)]),
            ("extra", False),
        ):
            doc = copy.deepcopy(original)
            doc[field] = value
            cases.append(doc)
        for field, value in (
            ("issuer", "publisher\n"),
            ("not_before", True),
            ("capabilities", ["motion.follow"]),
            ("extra", False),
        ):
            doc = copy.deepcopy(original)
            doc["keys"][0][field] = value
            cases.append(doc)
        for doc in cases:
            with self.subTest(doc=doc):
                with self.assertRaises(ValidationError):
                    check.validate(doc)

    def test_schema_success_is_not_authentication_or_time_validity(self):
        check = validator("passport-policy-v1.schema.json")
        case = first_case()
        original = json.loads(case["policy"])
        check.validate(original)
        validator("passport-envelope-v1.schema.json").validate(json.loads(case["envelope"]))
        positive = passports.verify(
            case["envelope"].encode(), case["policy"].encode(), **case["arguments"]
        )
        self.assertEqual(
            (positive.status, positive.reason), ("authenticated", "signature_verified")
        )
        invalid = []
        expired = copy.deepcopy(original)
        expired["expires_at"] = 1500
        invalid.append((expired, "policy_not_current"))
        revoked = copy.deepcopy(original)
        revoked["revoked_passports"] = ["fixture-statement-1"]
        invalid.append((revoked, "revoked"))
        wrong_key = copy.deepcopy(original)
        wrong_key["keys"][0]["public_key"] = "0" * 64
        invalid.append((wrong_key, "invalid_input"))
        for policy, reason in invalid:
            check.validate(policy)
            result = passports.verify(
                case["envelope"].encode(), json.dumps(policy).encode(), **case["arguments"]
            )
            self.assertEqual(result.status, "rejected")
            self.assertEqual(result.reason, reason)
            self.assertFalse(result.motion_authority)
        # JSON Schema's mathematical integer accepts 1.0; wire parsing must not.
        payload = json.loads((ROOT / "examples/passports/vectors.json").read_bytes())[
            "canonical_payload"
        ]
        doc = json.loads(payload)
        doc["version"] = 1.0
        validator("passport-v1.schema.json").validate(doc)
        with self.assertRaises(ValueError):
            passports.canonicalize(json.dumps(doc).encode())


@unittest.skipIf(Draft202012Validator is None, "install optional passport conformance requirements")
class InteropSchemaConformance(unittest.TestCase):
    def schema(self, kind):
        name = kind + "-v1.schema.json"
        self.assertTrue((ROOT / "contracts/interop" / name).is_file(), name)
        return validator(name)

    def cases(self, kind):
        return json.loads((ROOT / "examples/interop" / (kind + "-vectors-v1.json")).read_bytes())[
            "cases"
        ]

    def document(self, kind):
        return json.loads(self.cases(kind)[0][kind])

    def reject(self, kind, doc):
        with self.assertRaises(ValidationError):
            self.schema(kind).validate(doc)
        with self.assertRaises(ValueError):
            if kind == "task":
                interop_tasks.canonicalize_task(json.dumps(doc).encode())
            else:
                interop_federation._snapshot(doc)

    def test_portable_shapes_do_not_replace_authenticated_runtime(self):
        for kind in ("task", "federation"):
            check = self.schema(kind)
            for case in self.cases(kind):
                doc = json.loads(case[kind])
                if case["reason"] == "invalid_input":
                    with self.assertRaises(ValidationError):
                        check.validate(doc)
                else:
                    check.validate(doc)
                if kind == "task":
                    result = interop_tasks.validate_task(case["task"].encode(), **case["arguments"])
                else:
                    result = interop_federation.verify_federated_bundle(
                        *(
                            case[key].encode()
                            for key in ("federation", "task", "envelope", "policy")
                        ),
                        tuple(bytes.fromhex(value) for value in case["evidence_hex"]),
                        **case["arguments"],
                    )
                self.assertEqual((result.status, result.reason), (case["status"], case["reason"]))
                self.assertIs(result.execution_authority, False)
                self.assertIs(result.motion_authority, False)
                self.assertIs(result.evidence_verified, False)

    def test_closed_objects_and_safe_scalar_bounds(self):
        for kind in ("task", "federation"):
            self.schema(kind)
            original = self.document(kind)
            for field in original:
                changed = copy.deepcopy(original)
                del changed[field]
                with self.subTest(kind=kind, missing=field):
                    self.reject(kind, changed)
            for field, value in (
                ("extra", False),
                ("version", True),
                ("version", 2),
                ("issued_at", False),
                ("issued_at", -1),
                ("expires_at", 2**53),
            ):
                with self.subTest(kind=kind, field=field, value=value):
                    self.reject(kind, dict(original, **{field: value}))
            field = "task_id" if kind == "task" else "local_domain"
            for value in ("", "a" * 65, "x\n", "x\r", "x\u2028", "x\u2029", "é"):
                self.reject(kind, dict(original, **{field: value}))
        peer = self.document("federation")["peers"][0]
        for field in (*peer, "extra"):
            doc = self.document("federation")
            if field == "extra":
                doc["peers"][0][field] = False
            else:
                del doc["peers"][0][field]
            self.reject("federation", doc)

    def test_task_kind_evidence_and_budget_constraints(self):
        check = self.schema("task")
        original = self.document("task")
        for field in ("subject_sha256", "passport_sha256", "policy_sha256"):
            for value in ("A" * 64, "a" * 63, "a" * 64 + "\n", False):
                self.reject("task", dict(original, **{field: value}))
        for field, value in (
            ("kind", "shell.exec"),
            ("motion_authority", True),
            ("motion_authority", 0),
            ("evidence_sha256", []),
            ("evidence_sha256", ["d" * 64] * 2),
            ("evidence_sha256", [format(i, "064x") for i in range(17)]),
            ("max_evidence_bytes", 0),
            ("max_evidence_bytes", True),
            ("max_evidence_bytes", 1048577),
        ):
            self.reject("task", dict(original, **{field: value}))
        for count, budget in ((1, 1), (16, 1048576)):
            doc = dict(
                original,
                evidence_sha256=[format(i, "064x") for i in range(count)],
                max_evidence_bytes=budget,
            )
            check.validate(doc)
            interop_tasks.canonicalize_task(json.dumps(doc).encode())
        doc = dict(original, kind="passport.verify.v1", evidence_sha256=[], max_evidence_bytes=0)
        check.validate(doc)
        interop_tasks.canonicalize_task(json.dumps(doc).encode())
        for field, value in (("evidence_sha256", ["d" * 64]), ("max_evidence_bytes", 1)):
            self.reject("task", dict(doc, **{field: value}))

    def test_federation_collection_bounds_and_scopes(self):
        check = self.schema("federation")
        original = self.document("federation")
        for count in (0, 16):
            doc = copy.deepcopy(original)
            doc["peers"] = [
                dict(original["peers"][0], remote_domain=f"peer-{i}") for i in range(count)
            ]
            check.validate(doc)
            interop_federation._snapshot(doc)
        for field, value in (
            ("revision", 0),
            ("revision", True),
            ("revision", 2**53),
            ("peers", original["peers"] * 2),
            ("peers", [dict(original["peers"][0], remote_domain=f"peer-{i}") for i in range(17)]),
        ):
            self.reject("federation", dict(original, **{field: value}))
        for field, value in (
            ("issuers", []),
            ("issuers", ["a"] * 2),
            ("issuers", [f"issuer-{i}" for i in range(17)]),
            ("capabilities", []),
            ("capabilities", ["shell.exec"]),
            ("capabilities", ["evidence.offline.v1"] * 2),
            ("remote_domain", "peer\n"),
            ("policy_sha256", "A" * 64),
        ):
            doc = copy.deepcopy(original)
            doc["peers"][0][field] = value
            self.reject("federation", doc)
        doc = copy.deepcopy(original)
        doc["peers"][0].update(
            issuers=[f"issuer-{i}" for i in range(16)],
            capabilities=["perception.direct.v3", "presence.coarse.v2", "evidence.offline.v1"],
        )
        check.validate(doc)
        interop_federation._snapshot(doc)

    def test_structural_success_still_requires_semantic_and_lexical_checks(self):
        for kind, lifetime in (("task", 300), ("federation", 3600)):
            check = self.schema(kind)
            for start, end in ((1000, 1000), (1000, 1000 + lifetime + 1)):
                doc = dict(self.document(kind), issued_at=start, expires_at=end)
                check.validate(doc)
                with self.assertRaises(ValueError):
                    if kind == "task":
                        interop_tasks.canonicalize_task(json.dumps(doc).encode())
                    else:
                        interop_federation._snapshot(doc)
            doc = dict(self.document(kind), version=1.0)
            check.validate(doc)
            with self.assertRaises(ValueError):
                passports._parse(json.dumps(doc).encode())
        for duplicate_domain in (False, True):
            doc = self.document("federation")
            if duplicate_domain:
                doc["peers"].append(dict(doc["peers"][0], issuers=["different-issuer"]))
            else:
                doc["peers"][0]["remote_domain"] = doc["local_domain"]
            self.schema("federation").validate(doc)
            with self.assertRaises(ValueError):
                interop_federation._snapshot(doc)


@unittest.skipIf(Draft202012Validator is None, "install optional passport conformance requirements")
class EdgeEvidenceConformance(unittest.TestCase):
    def vectors(self):
        path = ROOT / "examples/interop/edge-unknown-vectors-v1.json"
        self.assertTrue(path.is_file(), "published edge UNKNOWN binding vectors required")
        return json.loads(path.read_bytes())

    def test_published_sources_and_independent_edge_structure(self):
        vectors = self.vectors()
        expected = {
            "contracts/openapi/aethron-edge-v1.json": "4d562382b803e59dac1ab24a7ead52cd2cdbbc9533aa6d9dc68fca9f6e9b0b83",
            "contracts/fixtures/v3/unknown-output.json": "2b91d797820cce663134417d5b52b016aebcaca02c7a710bc16984487b35a754",
        }
        self.assertEqual(vectors["source_sha256"], expected)
        self.assertEqual(vectors["source_commit"], "a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46")
        for path, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        api = json.loads((ROOT / "contracts/openapi/aethron-edge-v1.json").read_bytes())
        self.assertEqual(api["openapi"], "3.1.1")
        check = Draft202012Validator(
            {"$ref": "#/components/schemas/V3Snapshot", "components": api["components"]},
            registry=Registry(retrieve=deny_retrieval),
        )
        doc = json.loads((ROOT / "contracts/fixtures/v3/unknown-output.json").read_bytes())
        check.validate(doc)
        self.assertEqual(doc["state"], "UNKNOWN")
        self.assertEqual(doc["tracks"], [])
        self.assertIsNone(doc["evidence"])
        self.assertIs(doc["recommendation"]["requires_independent_controller"], True)
        for field, value in (("state", "SAFE"), ("motion_authority", True)):
            with self.assertRaises(ValidationError):
                check.validate(dict(doc, **{field: value}))
        changed = copy.deepcopy(doc)
        changed["recommendation"]["requires_independent_controller"] = False
        with self.assertRaises(ValidationError):
            check.validate(changed)

    def test_exact_binding_and_negative_portable_cases(self):
        cases = self.vectors()["cases"]
        self.assertEqual(
            [case["name"] for case in cases],
            [
                "unknown-bytes-bind",
                "reserialized-bytes",
                "changed-state",
                "missing-evidence",
                "expired-task",
                "revoked-evidence",
            ],
        )
        source = (ROOT / "contracts/fixtures/v3/unknown-output.json").read_bytes()
        for case in cases:
            with self.subTest(case=case["name"]):
                evidence = tuple(bytes.fromhex(blob) for blob in case["evidence_hex"])
                result = interop_bundles.verify_task_bundle(
                    *(case[key].encode() for key in ("task", "envelope", "policy")),
                    evidence,
                    **case["arguments"],
                )
                self.assertEqual((result.status, result.reason), (case["status"], case["reason"]))
                self.assertEqual([item.outcome for item in result.evidence], case["outcomes"])
                self.assertIs(result.execution_authority, False)
                self.assertIs(result.motion_authority, False)
                self.assertIs(result.evidence_verified, False)
                if case["name"] == "unknown-bytes-bind":
                    self.assertEqual(evidence, (source,))
                    self.assertEqual(result.evidence[0].kind, "synthetic")
                    self.assertEqual(result.evidence[0].sha256, hashlib.sha256(source).hexdigest())
                    self.assertEqual(result.expires_at, 1700)
                else:
                    self.assertIsNone(result.task_sha256)
                    self.assertIsNone(result.passport_sha256)
                    self.assertIsNone(result.expires_at)
                    self.assertEqual(result.evidence, ())
                if case["name"] == "reserialized-bytes":
                    self.assertNotEqual(evidence[0], source)
                    self.assertEqual(json.loads(evidence[0]), json.loads(source))
                if case["name"] == "changed-state":
                    self.assertEqual(json.loads(evidence[0])["state"], "PRESENT")

    def test_binding_does_not_translate_scene_clocks_or_make_observations_current(self):
        case = self.vectors()["cases"][0]
        source = bytes.fromhex(case["evidence_hex"][0])
        doc = json.loads(source)
        result = interop_bundles.verify_task_bundle(
            *(case[key].encode() for key in ("task", "envelope", "policy")),
            (source,),
            **case["arguments"],
        )
        self.assertEqual(result.status, "bound")
        self.assertEqual((doc["at_ms"], doc["expires_at_ms"]), (600, 800))
        self.assertEqual(result.expires_at, 1700)  # UTC seconds, not scene monotonic ms.
        self.assertEqual(result.evidence[0].outcome, "unknown")
        self.assertIs(result.evidence_verified, False)
        self.assertEqual(json.loads(source), doc)


@unittest.skipIf(Draft202012Validator is None, "install optional passport conformance requirements")
class ArchitectureDecisionConformance(unittest.TestCase):
    def document(self):
        return json.loads((ROOT / "docs/decisions/p16-policy-admission-v1.json").read_bytes())

    def test_published_decisions_validate_offline(self):
        paths = sorted((ROOT / "docs/decisions").glob("p16-*.json"))
        self.assertTrue(paths, "no P16 decision records were checked")
        check = validator("architecture-decision-v1.schema.json")
        for path in paths:
            with self.subTest(path=path.name):
                check.validate(json.loads(path.read_bytes()))

    def test_decisions_reject_missing_extra_and_unbounded_fields(self):
        check = validator("architecture-decision-v1.schema.json")
        original = self.document()
        for field in original:
            doc = copy.deepcopy(original)
            del doc[field]
            with self.subTest(missing=field):
                with self.assertRaises(ValidationError):
                    check.validate(doc)
        for field, value in (
            ("extra", True),
            ("version", True),
            ("version", 2),
            ("decision", "APPROVED"),
            ("id", "decision\n"),
            ("component", "x" * 161),
            ("alternatives", []),
            ("constraints", [""]),
            ("rationale", ["x"] * 2),
            ("limits", [str(i) for i in range(17)]),
            ("evidence", []),
        ):
            doc = copy.deepcopy(original)
            doc[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError):
                    check.validate(doc)

    def test_references_reject_without_optional_format_checker(self):
        check = validator("architecture-decision-v1.schema.json")
        self.assertIsNone(check.format_checker)
        for reference in (
            "not a URI",
            "http://example.com/",
            "https://example.com/\n",
            "https://example.com/\u2028",
            "https://example.com/" + "x" * 500,
        ):
            doc = self.document()
            doc["evidence"] = [reference]
            with self.subTest(reference=reference):
                with self.assertRaises(ValidationError):
                    check.validate(doc)
        # Demonstrate sensitivity to the regression seen in the manual check.
        # This mutates only a local schema copy; no project file is rewritten.
        weakened = copy.deepcopy(check.schema)
        del weakened["properties"]["evidence"]["items"]["pattern"]
        doc = self.document()
        doc["evidence"] = ["not a URI"]
        self.assertTrue(check.evolve(schema=weakened).is_valid(doc))
        self.assertFalse(check.is_valid(doc))


if __name__ == "__main__":
    unittest.main()
