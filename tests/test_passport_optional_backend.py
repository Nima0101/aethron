"""Exercise missing optional crypto in a fresh interpreter, without import mocks."""

# Trusted interpreter, fixed code and no shell; see the P16 trust reassessment.
import json
import subprocess  # nosec B404
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = """
import importlib.util
import json
import sys
backend_visible = importlib.util.find_spec('cryptography') is not None
sys.path.insert(0, sys.argv[1])
from aethron.passports import verify
case = json.load(sys.stdin)
result = verify(case['envelope'].encode(), case['policy'].encode(), **case['arguments'])
print(json.dumps({
    'backend_visible': backend_visible,
    'isolated': sys.flags.isolated,
    'no_site': sys.flags.no_site,
    'status': result.status,
    'reason': result.reason,
    'payload_sha256': result.payload_sha256,
    'policy_revision': result.policy_revision,
    'expires_at': result.expires_at,
    'motion_authority': result.motion_authority,
    'evidence_verified': result.evidence_verified,
}))
"""


class OptionalBackendTests(unittest.TestCase):
    def test_no_site_process_rejects_valid_signature_without_metadata(self):
        case = json.loads((ROOT / "examples/passports/vectors.json").read_bytes())["cases"][0]
        self.assertEqual((case["status"], case["reason"]), ("authenticated", "signature_verified"))
        for optimization in ([], ["-O"]):
            with self.subTest(optimization=optimization):
                # Fixed argv; the fixture is stdin data, never executable code.
                child = subprocess.run(  # nosec B603
                    [sys.executable, "-I", "-S", *optimization, "-c", PROBE, str(ROOT)],
                    input=json.dumps(case),
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(child.returncode, 0, child.stderr)
                self.assertEqual(child.stderr, "")
                self.assertEqual(
                    json.loads(child.stdout),
                    {
                        "backend_visible": False,
                        "isolated": 1,
                        "no_site": 1,
                        "status": "rejected",
                        "reason": "crypto_unavailable",
                        "payload_sha256": None,
                        "policy_revision": None,
                        "expires_at": None,
                        "motion_authority": False,
                        "evidence_verified": False,
                    },
                )
