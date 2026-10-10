"""Resource limits, loss handling and lifetime tests for opaque offline inboxes."""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from threading import Barrier

from aethron.interop_inbox import BoundedInbox


class InboxTests(unittest.TestCase):
    def test_rejected_put_still_purges_and_advances_clock(self):
        q = BoundedInbox()
        q.put("peer", b"expired", now_ms=0, expires_at_ms=10)
        q.put("peer", b"current", now_ms=0, expires_at_ms=20)
        result = q.put("peer", b"", now_ms=10, expires_at_ms=20)
        self.assertEqual(
            (result.reason, result.items, result.payload_bytes), ("invalid_input", 1, 7)
        )
        self.assertIsNone(result.payload)
        self.assertEqual(q.take(now_ms=10).payload, b"current")
        self.assertEqual(q.take(now_ms=9).reason, "clock_fault")
        self.assertEqual(q.take(now_ms=10).reason, "closed")

    def test_close_does_not_erase_previously_dequeued_bytes(self):
        q = BoundedInbox()
        payload = b"public synthetic artifact"
        q.put("peer", payload, now_ms=0, expires_at_ms=10)
        taken = q.take(now_ms=1)
        self.assertEqual((taken.status, taken.items, taken.payload_bytes), ("dequeued", 0, 0))
        q.close()
        closed = q.take(now_ms=2)
        self.assertEqual((closed.reason, closed.items, closed.payload_bytes), ("closed", 0, 0))
        self.assertIsNone(closed.payload)
        self.assertEqual(taken.payload, payload)
        # repr suppression is not redaction for other serialization methods.
        self.assertNotIn(payload.decode(), repr(taken))
        self.assertEqual(asdict(taken)["payload"], payload)
        for field in ("execution_authority", "motion_authority", "evidence_verified"):
            self.assertIs(asdict(taken)[field], False)

    def test_invalid_put_clock_closes_without_retaining_incoming_payload(self):
        q = BoundedInbox()
        q.put("peer", b"old", now_ms=10, expires_at_ms=20)
        result = q.put("peer", b"new", now_ms=9, expires_at_ms=20)
        self.assertEqual((result.reason, result.items, result.payload_bytes), ("clock_fault", 0, 0))
        self.assertIsNone(result.payload)
        self.assertIsNone(result.peer)
        self.assertIsNone(result.expires_at_ms)
        self.assertEqual(q.take(now_ms=11).reason, "closed")

    def test_concurrent_admission_cannot_overbook(self):
        q = BoundedInbox(max_items=8, max_bytes=8, max_per_peer=8)
        barrier = Barrier(2)

        def producer():
            barrier.wait(timeout=5)
            return [q.put("peer", b"x", now_ms=0, expires_at_ms=20) for _ in range(8)]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(producer) for _ in range(2)]
            results = [result for future in futures for result in future.result(timeout=10)]
        self.assertEqual(sum(r.status == "queued" for r in results), 8)
        self.assertTrue(all(r.items <= 8 and r.payload_bytes <= 8 for r in results))
        self.assertEqual([q.take(now_ms=1).payload for _ in range(8)], [b"x"] * 8)
        self.assertEqual(q.take(now_ms=1).status, "empty")

    def test_portable_traces(self):
        path = Path(__file__).resolve().parents[1] / "examples/interop/inbox-vectors-v1.json"
        for case in json.loads(path.read_bytes())["cases"]:
            q = BoundedInbox(**case["limits"])
            for operation in case["operations"]:
                args = dict(operation["arguments"])
                if "payload_hex" in args:
                    args["payload"] = bytes.fromhex(args.pop("payload_hex"))
                result = getattr(q, operation["method"])(**args)
                self.assertEqual(
                    [result.status, result.reason, result.items, result.payload_bytes],
                    operation["expected"],
                    case["name"],
                )
                self.assertEqual(
                    result.payload.hex() if result.payload is not None else None,
                    operation["payload_hex"],
                )
                self.assertFalse(result.motion_authority)
                self.assertFalse(result.execution_authority)
                self.assertFalse(result.evidence_verified)

    def test_fifo_and_exact_bytes_without_authority(self):
        q = BoundedInbox()
        for value in (b"one", b"two"):
            r = q.put("peer", value, now_ms=1, expires_at_ms=20)
            self.assertEqual(r.status, "queued")
            self.assertIsNone(r.payload)
            self.assertFalse(r.motion_authority)
        for value in (b"one", b"two"):
            r = q.take(now_ms=2)
            self.assertEqual((r.status, r.peer, r.payload), ("dequeued", "peer", value))
        self.assertEqual(q.take(now_ms=2).status, "empty")

    def test_quotas_reject_incoming_preserve_old_and_release(self):
        q = BoundedInbox(max_items=2, max_bytes=6, max_per_peer=1)
        self.assertEqual(q.put("a", b"1234", now_ms=0, expires_at_ms=20).status, "queued")
        self.assertEqual(q.put("a", b"1", now_ms=0, expires_at_ms=20).reason, "peer_capacity")
        self.assertEqual(q.put("b", b"123", now_ms=0, expires_at_ms=20).reason, "byte_capacity")
        r = q.put("b", b"12", now_ms=0, expires_at_ms=20)
        self.assertEqual((r.items, r.payload_bytes), (2, 6))
        self.assertEqual(q.put("c", b"1", now_ms=0, expires_at_ms=20).reason, "item_capacity")
        self.assertEqual(q.take(now_ms=1).payload, b"1234")
        self.assertEqual(q.put("a", b"1234", now_ms=1, expires_at_ms=20).status, "queued")
        self.assertEqual(q.take(now_ms=1).payload, b"12")

    def test_expiry_behind_live_head_and_exclusive_boundary(self):
        q = BoundedInbox(max_items=2, max_bytes=6, max_per_peer=2)
        q.put("a", b"abc", now_ms=0, expires_at_ms=20)
        q.put("b", b"xyz", now_ms=0, expires_at_ms=10)
        self.assertEqual(q.put("b", b"new", now_ms=10, expires_at_ms=20).status, "queued")
        self.assertEqual(q.take(now_ms=10).payload, b"abc")
        r = q.take(now_ms=20)
        self.assertEqual((r.status, r.items, r.payload_bytes), ("empty", 0, 0))

    def test_clock_failure_clears_and_closes(self):
        for clock in (-1, True, 1.0, 2**53, "1", 9):
            q = BoundedInbox()
            q.put("peer", b"synthetic", now_ms=10, expires_at_ms=20)
            r = q.take(now_ms=clock)
            self.assertEqual(
                (r.status, r.reason, r.items, r.payload_bytes), ("rejected", "clock_fault", 0, 0)
            )
            self.assertIsNone(r.payload)
            self.assertEqual(q.take(now_ms=11).reason, "closed")
            self.assertEqual(q.put("peer", b"new", now_ms=11, expires_at_ms=20).reason, "closed")

    def test_input_bounds_and_exact_types(self):
        class BytesSubclass(bytes):
            pass

        for blob in (
            b"",
            b"x" * 65537,
            bytearray(b"x"),
            memoryview(b"x"),
            BytesSubclass(b"x"),
            None,
        ):
            q = BoundedInbox()
            self.assertEqual(
                q.put("peer", blob, now_ms=0, expires_at_ms=20).reason, "invalid_input"
            )
        for peer in ("bad\n", "", None, "a" * 129):
            self.assertEqual(
                BoundedInbox().put(peer, b"x", now_ms=0, expires_at_ms=20).reason, "invalid_input"
            )
        for end in (True, 1.0, 0, 60001, 2**53):
            self.assertEqual(
                BoundedInbox().put("peer", b"x", now_ms=0, expires_at_ms=end).reason,
                "invalid_input",
            )
        for kwargs in (
            {"max_items": True},
            {"max_items": 17},
            {"max_bytes": 1048577},
            {"max_bytes": 0},
            {"max_per_peer": 0},
            {"max_items": 1, "max_per_peer": 2},
        ):
            with self.assertRaisesRegex(ValueError, "invalid_limits"):
                BoundedInbox(**kwargs)

    def test_close_and_maximum_capacity(self):
        q = BoundedInbox()
        for i in range(16):
            r = q.put(str(i), b"x" * 65536, now_ms=0, expires_at_ms=60000)
            self.assertEqual(r.status, "queued")
        self.assertEqual((r.items, r.payload_bytes), (16, 1048576))
        q.close()
        q.close()
        r = q.take(now_ms=0)
        self.assertEqual((r.reason, r.items, r.payload_bytes), ("closed", 0, 0))


if __name__ == "__main__":
    unittest.main()
