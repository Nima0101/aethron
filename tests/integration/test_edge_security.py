import tempfile
import unittest
from pathlib import Path

from aethron_edge.config import Credential, Profile
from aethron_edge.contracts import Principal
from aethron_edge.pipeline import RuntimePipeline
from aethron_edge.service.auth import Auth


class Security(unittest.TestCase):
    def test_unicode_bearer_is_fixed_unauthorized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("a" * 64)
            path.chmod(0o600)
            auth = Auth(
                [
                    Credential(
                        token_file=str(path), principal=Principal(name="test", scopes=["observe"])
                    )
                ]
            )
            self.assertIsNone(auth.authenticate("Bearer " + "\xff" * 64))

    def test_startup_unknown_keeps_configured_recommendation(self):
        p = RuntimePipeline(
            Profile(name="front", driver="file", address="unopened", contract="vehicle_stop")
        )
        import time

        result = p.snapshot(time.monotonic_ns())
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(result["recommendation"]["action"], "STOP")
        p.close()
