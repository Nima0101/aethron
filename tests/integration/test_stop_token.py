import multiprocessing as mp
import threading
import time
import unittest

from aethron_edge.mailbox import StopToken


def waiting(token, ready):
    ready.send(True)
    token.wait(30)


class StopAfterCrash(unittest.TestCase):
    def test_killed_waiter_cannot_block_stop_request(self):
        ctx = mp.get_context("spawn")
        token = StopToken(ctx)
        reader, writer = ctx.Pipe(duplex=False)
        worker = ctx.Process(target=waiting, args=(token, writer))
        worker.start()
        try:
            self.assertTrue(reader.poll(10))
            reader.recv()
            time.sleep(0.05)
            worker.kill()
            worker.join(timeout=2)
            request = threading.Thread(target=token.set, daemon=True)
            request.start()
            request.join(timeout=0.1)
            self.assertFalse(request.is_alive())
            self.assertTrue(token.is_set())
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=2)
            worker.close()
            reader.close()
            writer.close()
