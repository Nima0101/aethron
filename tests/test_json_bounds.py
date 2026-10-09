"""Differential checks against the frozen pre-allocation byte scan."""

import importlib.machinery
import itertools
import json
import os
import random
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron import _json_bounds, schema


def reference(data):
    if type(data) is not bytes or len(data) > 65536:
        return False
    depth = 0
    quoted = escaped = False
    for char in data:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > 8:
                return False
        elif char in (93, 125):
            depth -= 1
            if depth < 0:
                return False
    return True


class JsonBounds(unittest.TestCase):
    def test_installed_backend_and_python_fallback(self):
        if os.environ.get("AETHRON_EXPECT_NATIVE_BOUNDS") == "1":
            self.assertTrue(
                any(
                    _json_bounds.__file__.endswith(suffix)
                    for suffix in importlib.machinery.EXTENSION_SUFFIXES
                )
            )
        source = Path(_json_bounds.__file__).with_name("_json_bounds.py")
        fallback = runpy.run_path(str(source))["check"]
        for data in (b'"[\\"]"', b"[" * 9, b"]", b" " * 65536, b" " * 65537):
            self.assertEqual(_json_bounds.check(data), fallback(data))

    def test_exhaustive_structural_sequences_and_seeded_bytes(self):
        for size in range(6):
            for values in itertools.product(b'"\\[]{}x', repeat=size):
                data = bytes(values)
                self.assertEqual(_json_bounds.check(data), reference(data), data)
        rng = random.Random(20261009)
        for _ in range(2000):
            data = bytes(rng.randrange(256) for _ in range(rng.randrange(1025)))
            self.assertEqual(_json_bounds.check(data), reference(data))

    def test_budget_types_and_extreme_strings(self):
        for data in (None, "[]", bytearray(b"[]"), memoryview(b"[]"), 0):
            self.assertFalse(_json_bounds.check(data))

        class BytesSubclass(bytes):
            pass

        self.assertFalse(_json_bounds.check(BytesSubclass(b"[]")))
        for data in (
            b"[" * 8 + b"]" * 8,
            b"[" * 9,
            b"}" * 65536,
            b'"' + b"\\" * 65534 + b'"',
            b" " * 65536,
            b" " * 65537,
        ):
            self.assertEqual(_json_bounds.check(data), reference(data))

    def test_guard_runs_before_json_allocation(self):
        for data in (b"[" * 9 + b"]" * 9, b" " * 65537, b"]"):
            with patch.object(schema.json, "loads", side_effect=AssertionError("allocated")):
                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                    schema.parse(data)

    def test_full_parser_preserves_errors_and_values(self):
        # V1/V2/V3 fixtures run through their existing validators unchanged.
        root = Path(__file__).resolve().parents[1]
        cases = []
        for path in sorted((root / "examples").glob("*.jsonl")):
            cases.extend(path.read_bytes().splitlines()[:2])
        self.assertTrue(cases)
        cases += [
            b"{}",
            b'"\\uD800"',
            b'"\xff"',
            b'{"version":NaN}',
            b'[{"x":' * 9,
            b'{"version":3,"version":3}',
            b"null",
        ]

        def outcome(data):
            try:
                return json.dumps(schema.parse(data), sort_keys=True)
            except ValueError as exc:
                return type(exc), str(exc)

        for data in cases:
            actual = outcome(data)
            with patch.object(schema, "check_bounds", reference):
                expected = outcome(data)
            self.assertEqual(actual, expected)
