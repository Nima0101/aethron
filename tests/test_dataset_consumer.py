"""Immutable sample consumption bound to exact synthetic split/protocol bytes."""

import hashlib
import unittest
from unittest.mock import patch

import test_dataset_artifacts as fixtures

from aethron.evaluation import splits


@unittest.skipIf(
    getattr(fixtures.DatasetArtifacts, "__unittest_skip__", False),
    "POSIX artifact verification unavailable on this platform",
)
class DatasetConsumer(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DatasetArtifacts()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.raw = self.fixture.raw()
        self.manifest_digest = hashlib.sha256(self.raw).hexdigest()
        self.protocol_digest = self.fixture.doc["protocol_sha256"]

    def load(self, **changes):
        args = {
            "expected_manifest_sha256": self.manifest_digest,
            "expected_protocol_sha256": self.protocol_digest,
        }
        args.update(changes)
        return splits.load_split(self.raw, self.fixture.root, "test", **args)

    def test_prior_report_cannot_authorize_replaced_artifact(self):
        report = self.fixture.verify()
        self.assertTrue(report["artifacts_verified"])
        path = self.fixture.root / self.fixture.doc["samples"][2]["artifact_sha256"]
        path.write_bytes(b"replacement after verification")
        with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
            self.load()

    def test_returns_only_requested_split_as_immutable_bound_bytes(self):
        result = self.load()
        self.assertEqual(result.split, "test")
        self.assertEqual(result.manifest_sha256, self.manifest_digest)
        self.assertEqual(result.protocol_sha256, self.protocol_digest)
        self.assertFalse(result.rights_verified)
        self.assertFalse(result.qualified)
        self.assertEqual(len(result.samples), 1)
        sample = result.samples[0]
        self.assertEqual(sample.sample_id, "test")
        self.assertEqual(sample.data, b"original fixture 8")
        self.assertIs(type(sample.data), bytes)
        self.assertEqual(sample.evidence, "synthetic")
        self.assertEqual(sample.artifact_sha256, hashlib.sha256(sample.data).hexdigest())
        self.assertNotIn("original fixture", repr(result))
        with self.assertRaises(AttributeError):
            sample.data = b"mutated"
        with self.assertRaises(AttributeError):
            result.samples = ()
        path = self.fixture.root / sample.artifact_sha256
        path.write_bytes(b"later disk modification")
        self.assertEqual(sample.data, b"original fixture 8")

    def test_exact_manifest_and_protocol_pins_are_required(self):
        for changes in (
            {"expected_manifest_sha256": "0" * 64},
            {"expected_protocol_sha256": "0" * 64},
            {"expected_manifest_sha256": None},
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "^invalid_split_selection$"):
                    self.load(**changes)
        self.raw += b" "  # Same parsed document, different frozen input bytes.
        with self.assertRaisesRegex(ValueError, "^invalid_split_selection$"):
            self.load()

    def test_other_split_and_metadata_references_are_checked_before_return(self):
        for digest in (
            self.protocol_digest,
            self.fixture.doc["samples"][0]["artifact_sha256"],
            self.fixture.doc["provenance"][0]["rights_sha256"],
        ):
            with self.subTest(digest=digest):
                path = self.fixture.root / digest
                original = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                    self.load()
                path.write_bytes(original)

    def test_invalid_selection_rejected_before_filesystem_access(self):
        for selection in ("all", True, [], None):
            with self.subTest(selection=selection):
                with self.assertRaisesRegex(ValueError, "^invalid_split_selection$"):
                    splits.load_split(
                        self.raw,
                        self.fixture.root / "absent",
                        selection,
                        expected_manifest_sha256=self.manifest_digest,
                        expected_protocol_sha256=self.protocol_digest,
                    )

    def test_consumer_preserves_aggregate_limit(self):
        with patch.object(splits, "MAX_TOTAL_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                self.load()
