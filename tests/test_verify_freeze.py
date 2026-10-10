"""Freeze-check evidence from synthetic manifests, never product consumers."""

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class FreezeManifestChecks(unittest.TestCase):
    # Reuse the synthetic root and intercepted child boundaries, not its tests.
    fixture = static_checks.StaticCheckClaims.fixture

    def manifest(self, name, files, **metadata):
        path = verify.ROOT / "docs/verification" / name
        path.write_text(json.dumps({**metadata, "files": files}), encoding="utf-8")

    def payload(self, name, data=b"synthetic\x00bytes\r\n"):
        path = verify.ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    @contextlib.contextmanager
    def bounded_payload_reader(self, path, *, fail_after=None, short_reads=False):
        original_open = Path.open
        owner = self
        streams = []

        class Reader:
            def __init__(self, stream):
                self.stream = stream
                self.reads = 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def read(self, size=-1):
                owner.assertGreater(size, 0, "freeze payload read must be bounded")
                owner.assertLessEqual(size, 65536)
                if fail_after is not None and self.reads >= fail_after:
                    raise OSError("synthetic interrupted freeze read")
                self.reads += 1
                return self.stream.read(min(size, 7) if short_reads else size)

        def opened(candidate, *args, **kwargs):
            stream = original_open(candidate, *args, **kwargs)
            if candidate != path:
                return stream
            streams.append(stream)
            return Reader(stream)

        with patch.object(Path, "open", opened):
            yield
        self.assertTrue(streams)
        self.assertTrue(all(stream.closed for stream in streams))

    def test_payload_hashing_uses_bounded_reads_at_chunk_boundaries(self):
        for size in (0, 1, 65535, 65536, 65537, 131073):
            with self.subTest(size=size), self.fixture("value = 1") as (_, calls):
                digest = self.payload("fixture.bin", (bytes(range(256)) * 513)[:size])
                self.manifest("governance-freeze.json", {"fixture.bin": digest})
                with self.bounded_payload_reader(verify.ROOT / "fixture.bin"):
                    verify.run()
                self.assertEqual(len(calls), 5)

    def test_short_reads_are_not_treated_as_end_of_file(self):
        with self.fixture("value = 1") as (_, calls):
            digest = self.payload("fixture.bin", bytes(range(256)))
            self.manifest("governance-freeze.json", {"fixture.bin": digest})
            with self.bounded_payload_reader(verify.ROOT / "fixture.bin", short_reads=True):
                verify.run()
            self.assertEqual(len(calls), 5)

    def test_late_read_failure_closes_payload_and_prevents_success(self):
        with self.fixture("value = 1") as (output, calls):
            digest = self.payload("fixture.bin", b"x" * 65537)
            self.manifest("governance-freeze.json", {"fixture.bin": digest})
            with self.bounded_payload_reader(verify.ROOT / "fixture.bin", fail_after=1):
                with self.assertRaisesRegex(OSError, "synthetic interrupted freeze read"):
                    verify.run()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_each_manifest_checks_exact_bytes(self):
        for name in (
            "governance",
            "architecture",
            "amendment-v2",
            "data",
            "amendment-v3",
            "data-v3",
            "registration",
            "rgb-model",
            "rgb-smoke",
        ):
            for changed in (False, True):
                with (
                    self.subTest(name=name, changed=changed),
                    self.fixture("value = 1") as (output, calls),
                ):
                    digest = self.payload("fixture.bin")
                    self.manifest(name + "-freeze.json", {"fixture.bin": digest})
                    if changed:
                        self.payload("fixture.bin", b"changed")
                        with self.assertRaisesRegex(
                            AssertionError, "^freeze mismatch: fixture.bin$"
                        ):
                            verify.run()
                        self.assertEqual(output.getvalue(), "")
                        self.assertEqual(len(calls), 1)
                    else:
                        verify.run()
                        self.assertEqual(len(calls), 5)

    def test_historical_agents_use_versioned_file_not_current_file(self):
        for manifest, version in (("governance", 1), ("amendment-v2", 2)):
            for changed in (False, True):
                with (
                    self.subTest(manifest=manifest, changed=changed),
                    self.fixture("value = 1") as (output, calls),
                ):
                    archived = f"docs/engineering/history/AGENTS.v{version}.md"
                    digest = self.payload(archived, b"historical rules")
                    self.manifest(manifest + "-freeze.json", {"AGENTS.md": digest})
                    self.payload("AGENTS.md", b"current rules")
                    if changed:
                        self.payload(archived, b"changed historical rules")
                        # Even a matching current file cannot mask a changed archive.
                        self.payload("AGENTS.md", b"historical rules")
                        with self.assertRaisesRegex(AssertionError, "^freeze mismatch: AGENTS.md$"):
                            verify.run()
                        self.assertEqual(output.getvalue(), "")
                        self.assertEqual(len(calls), 1)
                    else:
                        verify.run()
                        self.assertEqual(len(calls), 5)

    def test_other_manifests_do_not_remap_agents(self):
        with self.fixture("value = 1") as (_, calls):
            digest = self.payload("AGENTS.md", b"current rules")
            self.manifest("architecture-freeze.json", {"AGENTS.md": digest})
            verify.run()
            self.assertEqual(len(calls), 5)

    def test_missing_or_malformed_inputs_prevent_success(self):
        for kind in ("manifest", "payload", "json"):
            with self.subTest(kind=kind), self.fixture("value = 1") as (output, calls):
                path = verify.ROOT / "docs/verification/governance-freeze.json"
                if kind == "manifest":
                    path.unlink()
                elif kind == "payload":
                    self.manifest(path.name, {"absent.bin": "0" * 64})
                else:
                    path.write_text("{", encoding="utf-8")
                with self.assertRaises(
                    json.JSONDecodeError if kind == "json" else FileNotFoundError
                ):
                    verify.run()
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(len(calls), 1)

    def test_metadata_and_unlisted_files_are_not_verified(self):
        with self.fixture("value = 1") as (_, calls):
            self.payload("unlisted.bin")
            self.manifest("governance-freeze.json", {}, version="unvalidated", stage="unvalidated")
            verify.run()
            self.assertEqual(len(calls), 5)

    def reject_manifest(self, body, message="invalid_freeze_manifest"):
        with self.fixture("value = 1") as (output, calls):
            path = verify.ROOT / "docs/verification/governance-freeze.json"
            path.write_bytes(body)
            with patch.object(verify, "local_sha256") as hashed:
                with self.assertRaises(Exception) as caught:
                    verify.run()
                self.assertIsInstance(caught.exception, ValueError)
                self.assertEqual(str(caught.exception), message)
                hashed.assert_not_called()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_duplicate_fields_cannot_replace_inventory_or_digest(self):
        for body in (
            b'{"files":{"absent":"bad"},"files":{}}',
            b'{"files":{},"fi\\u006ces":{}}',
            b'{"files":{"x":"bad","x":"' + b"0" * 64 + b'"}}',
            b'{"files":{},"metadata":{"v":1,"v":2}}',
        ):
            with self.subTest(body=body):
                self.reject_manifest(body)

    def test_invalid_inventory_rejected_before_any_payload_hash(self):
        for doc in (
            [],
            None,
            {},
            {"files": []},
            {"files": None},
            {"files": {"": "0" * 64}},
            {"files": {"x": 0}},
            {"files": {"x": "A" * 64}},
            {"files": {"x": "0" * 63}},
            {"files": {"first": "0" * 64, "second": False}},
        ):
            with self.subTest(doc=doc):
                self.reject_manifest(json.dumps(doc).encode())

    def test_manifest_byte_limit_accepts_exact_size_and_rejects_excess(self):
        body = b'{"files":{},"note":"\xc3\xa9"}'
        with patch.object(verify, "MAX_FREEZE_MANIFEST_BYTES", len(body), create=True):
            with self.fixture("value = 1"):
                path = verify.ROOT / "docs/verification/governance-freeze.json"
                path.write_bytes(body)
                verify.run()
            self.reject_manifest(body + b" ", "freeze_manifest_limit")

    def test_oversized_manifest_rejected_before_json_decode(self):
        with self.fixture("value = 1") as (output, calls):
            path = verify.ROOT / "docs/verification/governance-freeze.json"
            path.write_bytes(b" " * 33)
            with (
                patch.object(verify, "MAX_FREEZE_MANIFEST_BYTES", 32, create=True),
                patch.object(verify.json, "loads", side_effect=AssertionError("decoded excess")),
            ):
                with self.assertRaises(Exception) as caught:
                    verify.run()
                self.assertIsInstance(caught.exception, ValueError)
                self.assertEqual(str(caught.exception), "freeze_manifest_limit")
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_manifest_entry_limit_applies_before_payload_reads(self):
        with patch.object(verify, "MAX_FREEZE_MANIFEST_ENTRIES", 1, create=True):
            with self.fixture("value = 1"):
                digest = self.payload("fixture.bin")
                self.manifest("governance-freeze.json", {"fixture.bin": digest})
                verify.run()
            self.reject_manifest(
                json.dumps({"files": {"a": "0" * 64, "b": "0" * 64}}).encode(),
                "freeze_manifest_limit",
            )

    def test_manifest_growth_after_stat_is_rejected_before_decode(self):
        with self.fixture("value = 1") as (output, calls):
            path = verify.ROOT / "docs/verification/governance-freeze.json"
            body = path.read_bytes()
            original_open = Path.open
            owner = self

            class GrownFile(io.BytesIO):
                def read(self, size=-1):
                    owner.assertEqual(size, len(body) + 1)
                    return super().read(size)

            grown = GrownFile(body + b" " * 100)

            def opened(candidate, *args, **kwargs):
                return grown if candidate == path else original_open(candidate, *args, **kwargs)

            with (
                patch.object(verify, "MAX_FREEZE_MANIFEST_BYTES", len(body)),
                patch.object(Path, "open", opened),
                patch.object(verify.json, "loads", side_effect=AssertionError("decoded excess")),
            ):
                with self.assertRaisesRegex(ValueError, "^freeze_manifest_limit$"):
                    verify.run()
            self.assertTrue(grown.closed)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)
