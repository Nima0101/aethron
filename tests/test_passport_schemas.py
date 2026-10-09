"""Independent structural checks; schema validity never authenticates a passport."""

import copy
import json
import unittest
from pathlib import Path

from aethron import passports

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
        ):
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
        invalid = []
        expired = copy.deepcopy(original)
        expired["expires_at"] = 1500
        invalid.append(expired)
        revoked = copy.deepcopy(original)
        revoked["revoked_passports"] = ["fixture-statement-1"]
        invalid.append(revoked)
        wrong_key = copy.deepcopy(original)
        wrong_key["keys"][0]["public_key"] = "0" * 64
        invalid.append(wrong_key)
        for policy in invalid:
            check.validate(policy)
            result = passports.verify(
                case["envelope"].encode(), json.dumps(policy).encode(), **case["arguments"]
            )
            self.assertEqual(result.status, "rejected")
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


if __name__ == "__main__":
    unittest.main()
