"""Stalled verifier children stop completion and are reaped on timeout."""

import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class VerificationTimeouts(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    def test_each_timeout_preserves_failure_and_stops_later_checks(self):
        for stage in range(5):
            with self.subTest(stage=stage):
                calls = []
                error = subprocess.TimeoutExpired(
                    ["verification child"], 30, output=b"partial output", stderr=b"partial error"
                )

                def child(args, calls=calls, stage=stage, error=error, **kwargs):
                    calls.append((args, kwargs))
                    if len(calls) == stage + 1:
                        raise error
                    return subprocess.CompletedProcess(args, 0)

                with (
                    self.fixture("value = 1") as (output, _),
                    patch.object(verify.subprocess, "run", side_effect=child),
                ):
                    with self.assertRaises(subprocess.TimeoutExpired) as caught:
                        verify.run()
                self.assertIs(caught.exception, error)
                self.assertEqual(error.output, b"partial output")
                self.assertEqual(error.stderr, b"partial error")
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(len(calls), stage + 1)
                for index, (_, kwargs) in enumerate(calls):
                    self.assertEqual(kwargs.get("timeout"), (30, 600, 600, 30, 600)[index])

    def test_real_stalled_child_is_reaped_at_every_stage(self):
        invoke = subprocess.run
        popen = subprocess.Popen
        for stage in range(5):
            with self.subTest(stage=stage):
                children = []
                calls = []

                def spawn(*args, children=children, **kwargs):
                    process = popen(*args, **kwargs)
                    children.append(process)
                    return process

                def child(args, calls=calls, stage=stage, **kwargs):
                    calls.append(args)
                    if len(calls) != stage + 1:
                        return subprocess.CompletedProcess(args, 0)
                    return invoke(
                        [sys.executable, "-c", "import time; time.sleep(1)"],
                        cwd=kwargs["cwd"],
                        env=kwargs["env"],
                        check=kwargs["check"],
                        timeout=kwargs.get("timeout", 2),
                    )

                with (
                    self.fixture("value = 1") as (output, _),
                    patch.object(verify, "CHECK_TIMEOUT_SECONDS", 0.1, create=True),
                    patch.object(verify, "CONSUMER_TIMEOUT_SECONDS", 0.1, create=True),
                    patch.object(verify.subprocess, "run", side_effect=child),
                    patch.object(verify.subprocess, "Popen", side_effect=spawn),
                ):
                    with self.assertRaises(subprocess.TimeoutExpired):
                        verify.run()
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(len(calls), stage + 1)
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].returncode)
                self.assertIsNotNone(children[0].poll())
