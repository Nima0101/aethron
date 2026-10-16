"""Verifier children opt out before ORT import; the parent environment is unchanged."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from itertools import product
from pathlib import Path
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class VerificationTelemetry(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    def test_every_child_overrides_opt_in_without_mutating_parent(self):
        for inherited, user_site in product((None, "0", "1"), (None, "", "1")):
            # Mocked children need no host environment. Explicit states prevent
            # the caller's user-site opt-out from masking a missing child guard.
            environment = {
                "AETHRON_TEST_ENV_SENTINEL": "preserved",
                "PYTHONHOME": "foreign interpreter",
                "PYTHONPATH": "foreign modules",
            }
            if inherited is not None:
                environment["ORT_DISABLE_TELEMETRY"] = inherited
            if user_site is not None:
                environment["PYTHONNOUSERSITE"] = user_site
            with (
                self.subTest(inherited=inherited, user_site=user_site),
                patch.dict(os.environ, environment, clear=True),
            ):
                before = dict(os.environ)
                with self.fixture("value = 1"), patch.object(verify.subprocess, "run") as child:
                    verify.run()
                self.assertEqual(child.call_count, 5)
                expected = {
                    "AETHRON_TEST_ENV_SENTINEL": "preserved",
                    "ORT_DISABLE_TELEMETRY": "1",
                    "PYTHONNOUSERSITE": "1",
                }
                for call in child.call_args_list:
                    self.assertEqual(call.kwargs.get("env"), expected)
                    self.assertIsNot(call.kwargs["env"], os.environ)
                self.assertEqual(dict(os.environ), before)

    @unittest.skipUnless(importlib.util.find_spec("onnxruntime"), "optional ORT required")
    def test_native_child_inference_leaves_no_telemetry_file(self):
        # Synthetic Identity model from peer 56f0664's run-options probe, without
        # importing its unrelated cancellation/benchmark dependencies.
        probe = """
import os
assert os.environ['ORT_DISABLE_TELEMETRY'] == '1'
import numpy as np
import onnxruntime as ort
model = bytes.fromhex(
    '08083a420a100a017812017922084964656e74697479120c7032335f6964656e74697479'
    '5a0f0a0178120a0a08080112040a020801620f0a0179120a0a08080112040a0208014202100d'
)
options = ort.SessionOptions()
options.intra_op_num_threads = 1
options.inter_op_num_threads = 1
session = ort.InferenceSession(
    model, sess_options=options, providers=['CPUExecutionProvider'], enable_fallback=False
)
assert session.get_providers() == ['CPUExecutionProvider']
result, = session.run(['y'], {'x': np.array([3.25], dtype=np.float32)})
assert result.dtype == np.float32 and result.shape == (1,) and result.tolist() == [3.25]
print('native_inference_executed')
"""
        invoke = subprocess.run
        native_checked = False
        with tempfile.TemporaryDirectory() as directory:

            def check_child(args, **kwargs):
                nonlocal native_checked
                self.assertEqual(kwargs.get("env", {}).get("ORT_DISABLE_TELEMETRY"), "1")
                if "unittest" in args:
                    completed = invoke(
                        [sys.executable, "-I", "-c", probe],
                        cwd=directory,
                        env=kwargs["env"],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    self.assertEqual(completed.stdout.strip(), "native_inference_executed")
                    native_checked = True
                return subprocess.CompletedProcess(args, 0)

            with (
                patch.dict(os.environ, {"ORT_DISABLE_TELEMETRY": "0"}),
                self.fixture("value = 1"),
                patch.object(verify.subprocess, "run", side_effect=check_child),
            ):
                verify.run()
                self.assertEqual(os.environ["ORT_DISABLE_TELEMETRY"], "0")
            self.assertTrue(native_checked)
            self.assertEqual(list(Path(directory).iterdir()), [])
