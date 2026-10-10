"""The comparison probe must not emit evidence with assertions disabled."""

import subprocess
import sys
import unittest
from pathlib import Path


class ProbeExecutionTests(unittest.TestCase):
    def test_optimized_execution_is_rejected_without_evidence(self):
        root = Path(__file__).resolve().parents[1] / "scripts"
        for name in ("passport_technology_probe.py", "passport_trust_review.py"):
            for option in ("-O", "-OO"):
                with self.subTest(script=name, option=option):
                    result = subprocess.run(
                        [sys.executable, "-I", option, str(root / name)],
                        capture_output=True,
                        text=True,
                        timeout=25,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("optimized_probe_execution_forbidden", result.stderr)
                    self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
