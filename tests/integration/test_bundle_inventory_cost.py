"""Bound inventory interpreter work without weakening exact file/type checks."""

import cProfile
import tempfile
import unittest
from pathlib import Path

from aethron_edge.runtime.updates import _inventory


class InventoryCost(unittest.TestCase):
    def test_256_file_inventory_stays_below_ten_thousand_calls(self):
        # Operation budget avoids a host-load-dependent wall-time assertion.
        # It covers all calls, allowing any equivalent inventory implementation.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = {f"group-{i % 4}/file-{i}.py" for i in range(256)}
            for name in expected:
                file = root / name
                file.parent.mkdir(exist_ok=True)
                file.touch()
            profiler = cProfile.Profile()
            actual = profiler.runcall(_inventory, root)
            self.assertEqual(actual, expected)
            calls = sum(entry.callcount for entry in profiler.getstats())
            self.assertLess(calls, 10_000)


if __name__ == "__main__":
    unittest.main()
