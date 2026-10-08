import multiprocessing as mp
import time
import unittest

from aethron_edge.mailbox import Mailbox


def die_holding_slot(mailbox, ready):
    mailbox.lock.acquire()
    ready.set()
    time.sleep(30)


class MailboxSafety(unittest.TestCase):
    def test_killed_writer_does_not_block_watchdog_reader(self):
        import queue

        ctx = mp.get_context("spawn")
        mailbox = Mailbox(ctx)
        ready = ctx.Event()
        worker = ctx.Process(target=die_holding_slot, args=(mailbox, ready))
        worker.start()
        try:
            self.assertTrue(ready.wait(5))
            worker.kill()
            worker.join(timeout=2)
            start = time.monotonic()
            with self.assertRaises(queue.Empty):
                mailbox.get_nowait()
            self.assertLess(time.monotonic() - start, 0.02)
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=2)
            worker.close()

    def test_one_slot_replaces_old_without_history_and_rejects_large_message(self):
        import queue

        mailbox = Mailbox(mp.get_context("spawn"))
        mailbox.put_nowait({"data": b"first"})
        mailbox.put_nowait({"data": b"second"})
        self.assertEqual(mailbox.get_nowait()["data"], b"second")
        with self.assertRaises(queue.Empty):
            mailbox.get_nowait()
        with self.assertRaises(ValueError):
            mailbox.put_nowait({"data": b"x" * 65537})

    def test_drops_distinguish_overwrite_and_busy_rejection(self):
        import queue

        mailbox = Mailbox(mp.get_context("spawn"))
        mailbox.put_nowait({"data": b"old"})
        mailbox.put_nowait({"data": b"new"})
        self.assertEqual(mailbox.overwritten.value, 1)
        self.assertEqual(mailbox.rejected.value, 0)
        mailbox.lock.acquire()
        try:
            with self.assertRaises(queue.Full):
                mailbox.put_nowait({"data": b"busy"})
        finally:
            mailbox.lock.release()
        self.assertEqual(mailbox.rejected.value, 1)
        self.assertEqual(mailbox.get_nowait()["data"], b"new")
