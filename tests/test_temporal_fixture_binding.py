"""Standalone evaluation must consume the frozen synthetic fixture bytes."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import temporal_evaluate as temporal


class TemporalFixtureBinding(unittest.TestCase):
    def test_frozen_payload_is_returned_without_rereading(self):
        for path in temporal.synthetic_fixture_paths():
            payload = path.read_bytes()
            original = Path.read_bytes
            reads = []

            def read(candidate, path=path, reads=reads, payload=payload, original=original):
                if candidate == path:
                    reads.append(candidate)
                    return payload if len(reads) == 1 else b"[]"
                return original(candidate)

            with self.subTest(fixture=path.name), patch.object(Path, "read_bytes", read):
                self.assertEqual(temporal.synthetic_fixture_payload(path), payload)
            self.assertEqual(reads, [path])

    def test_shortened_fixture_cannot_publish_success(self):
        source = temporal.ROOT
        for fixture in sorted((source / "data/temporal").glob("*.json")):
            with self.subTest(fixture=fixture.name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(source / "data/temporal", root / "data/temporal")
                freeze = root / "docs/verification/data-v3-freeze.json"
                freeze.parent.mkdir(parents=True)
                shutil.copyfile(source / "docs/verification/data-v3-freeze.json", freeze)
                target = root / "data/temporal" / fixture.name
                target.write_text(json.dumps(json.loads(target.read_bytes())[:1]))
                output = root / "output"
                output.mkdir()
                report_path = output / "temporal-evaluation.json"
                report_path.write_text('{"passed": true, "stale": true}')
                with (
                    patch.object(temporal, "ROOT", root),
                    patch.object(temporal, "benchmark", return_value={"passed": True}) as bench,
                    patch.object(temporal, "recorded", return_value={}) as recorded,
                    contextlib.redirect_stdout(io.StringIO()) as stdout,
                ):
                    with self.assertRaisesRegex(ValueError, "^synthetic_fixture_digest$"):
                        temporal.run(output)
                bench.assert_not_called()
                recorded.assert_not_called()
                self.assertEqual(stdout.getvalue(), "")
                report = json.loads(report_path.read_bytes())
                self.assertIs(report["passed"], False)
                self.assertEqual(report["failure_stage"], "synthetic")
                self.assertNotIn(fixture.stem, report["synthetic"])
                self.assertNotIn("stale", report)


if __name__ == "__main__":
    unittest.main()
