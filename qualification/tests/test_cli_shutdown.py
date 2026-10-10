"""Real report processes must preserve fixed failure status on closed pipes."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from qualification.tests.test_campaign_bundle_cli import frame

ROOT = Path(__file__).resolve().parents[2]


class CliShutdownTests(unittest.TestCase):
    def closed_pipe(self, module, payload, args=()):
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        # No reader exists before the child starts: no timing/sleep dependency.
        with os.fdopen(write_fd, "wb") as target:
            result = subprocess.run(
                [sys.executable, "-E", "-m", module, *args],
                input=payload,
                stdout=target,
                stderr=subprocess.PIPE,
                cwd=ROOT,
                timeout=10,
                check=False,
            )
        return result.returncode, result.stderr

    def test_closed_stdout_preserves_fixed_failure_for_both_report_outcomes(self):
        for rig in ("synthetic-v1.json", "expired-calibration-v1.json"):
            with self.subTest(module="qualification", rig=rig):
                self.assertEqual(
                    self.closed_pipe(
                        "qualification",
                        (ROOT / "qualification/rigs" / rig).read_bytes(),
                        ["--now-ms", "1050"],
                    ),
                    (2, b"invalid_qualification_manifest\n"),
                )
        for raw in (frame(), frame(rows=[])):
            with self.subTest(module="qualification.campaign_bundle_cli", bytes=len(raw)):
                self.assertEqual(
                    self.closed_pipe("qualification.campaign_bundle_cli", raw),
                    (2, b"invalid_campaign_bundle\n"),
                )

    def test_input_failure_remains_fixed_when_stdout_is_also_closed(self):
        for module, args, diagnostic in (
            ("qualification", ["--now-ms", "1050"], b"invalid_qualification_manifest\n"),
            ("qualification.campaign_bundle_cli", [], b"invalid_campaign_bundle\n"),
        ):
            with self.subTest(module=module):
                self.assertEqual(
                    self.closed_pipe(module, b"PRIVATE malformed", args), (2, diagnostic)
                )
