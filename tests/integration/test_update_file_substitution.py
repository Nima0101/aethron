"""Updater reads must reject replacements before reading a substituted object."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.runtime.updates import UpdateStore, digest


class Substitution(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX file types")
    def test_substitution_before_open_is_rejected_without_blocking(self):
        for reader in ("digest", "state"):
            for kind in ("symlink", "fifo", "regular"):
                with self.subTest(reader=reader, kind=kind):
                    self.check_substitution(reader, kind)

    def check_substitution(self, reader, kind):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            store = UpdateStore(root, root / "unused-public-key")
            path = (store.root / "active.json") if reader == "state" else (root / "payload")
            content = b'{"slot":"1-aaaaaaaaaaaaaaaa","minimum_version":1}'
            path.write_bytes(content)
            target = root / "replacement"
            target.write_bytes(content)
            old = root / "old"
            path_open, descriptor_open = Path.open, os.open
            replaced = []

            def replace():
                if replaced:
                    return
                replaced.append(True)
                path.rename(old)
                if kind == "symlink":
                    path.symlink_to(target)
                elif kind == "fifo":
                    os.mkfifo(path)
                else:
                    target.rename(path)

            def legacy_open(candidate, *args, **kwargs):
                if candidate == path:
                    replace()
                    if kind == "fifo":
                        self.fail("blocking FIFO open attempted")
                return path_open(candidate, *args, **kwargs)

            def guarded_descriptor(candidate, flags, *args, **kwargs):
                if Path(candidate) == path:
                    replace()
                    self.assertTrue(flags & os.O_NONBLOCK)
                    self.assertTrue(flags & os.O_NOFOLLOW)
                return descriptor_open(candidate, flags, *args, **kwargs)

            with (
                patch.object(Path, "open", legacy_open),
                patch("os.open", guarded_descriptor),
            ):
                with self.assertRaises((ValueError, OSError)):
                    digest(path) if reader == "digest" else store._state()
            self.assertEqual(replaced, [True])
            self.assertEqual(old.read_bytes(), content)
