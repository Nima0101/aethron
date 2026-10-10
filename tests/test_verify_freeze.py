"""Freeze-check evidence from synthetic manifests, never product consumers."""

import hashlib
import json
import unittest

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
