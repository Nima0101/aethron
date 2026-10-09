"""Store locking must reject alias/special files and release on exceptions."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.runtime._store_lock import exclusive_store


class StoreLock(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / ".mutation.lock"

    def test_same_process_contention_and_exception_release(self):
        with self.assertRaisesRegex(RuntimeError, "test_interrupt"):
            with exclusive_store(self.root):
                with self.assertRaisesRegex(ValueError, "update_store_busy"):
                    with exclusive_store(self.root):
                        self.fail("second owner entered")
                raise RuntimeError("test_interrupt")
        inode = self.path.stat()
        with exclusive_store(self.root):
            self.assertTrue(os.path.samestat(inode, self.path.stat()))

    def test_hard_link_rejected_without_modifying_target(self):
        target = self.root / "unrelated"
        target.write_bytes(b"unchanged")
        os.link(target, self.path)
        with self.assertRaisesRegex(ValueError, "invalid_update_lock"):
            with exclusive_store(self.root):
                self.fail("aliased lock accepted")
        self.assertEqual(target.read_bytes(), b"unchanged")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_fifo_rejected_without_blocking(self):
        os.mkfifo(self.path)
        original = os.open

        def guarded_open(path, flags, mode=0o777):
            self.assertTrue(flags & os.O_NONBLOCK, "FIFO open must not block")
            return original(path, flags, mode)

        with patch("aethron_edge.runtime._store_lock.os.open", guarded_open):
            with self.assertRaisesRegex(ValueError, "invalid_update_lock"):
                with exclusive_store(self.root):
                    self.fail("FIFO lock accepted")

    @unittest.skipIf(os.name == "nt", "Windows may prevent open-file replacement")
    def test_replaced_lock_inode_rejected(self):
        original = os.open

        def replaced_after_open(path, flags, mode=0o777):
            fd = original(path, flags, mode)
            self.path.rename(self.root / "previous-lock")
            os.close(original(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            return fd

        with patch("aethron_edge.runtime._store_lock.os.open", replaced_after_open):
            with self.assertRaisesRegex(ValueError, "invalid_update_lock"):
                with exclusive_store(self.root):
                    self.fail("replaced lock accepted")
