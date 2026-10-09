"""Fleet exports contain only bounded, current software-health counts."""

import json
import random
import unittest
from types import SimpleNamespace

from aethron_edge.runtime.fleet_health import FleetHealth, encode_local_health


def report(state="running", emitted=1000, expires=3000, **extra):
    return json.dumps(
        dict(version=1, state=state, emitted_ms=emitted, status_expires_ms=expires, **extra)
    ).encode()


class FleetHealthTests(unittest.TestCase):
    def test_projection_excludes_all_unselected_supervisor_fields(self):
        status = json.loads(report())
        status.update(
            sensors={"private-site": {"geometry": "private"}},
            telemetry={"asset": "private"},
            credentials="private",
            qualified=True,
            scene_state="PRESENT",
        )
        raw = encode_local_health(status, now_ms=1000)
        self.assertEqual(json.loads(raw), json.loads(report()))
        self.assertNotIn(b"private", raw)
        self.assertLessEqual(len(raw), 256)

    def test_counts_preserve_unknown_slots_without_identity_or_safety_claim(self):
        fleet = FleetHealth(5)
        for slot, state in enumerate(("running", "recovering", "fault", "stopped")):
            self.assertTrue(fleet.ingest(slot, report(state), now_ms=1000))
        self.assertEqual(
            fleet.snapshot(now_ms=1000),
            {
                "version": 1,
                "total": 5,
                "states": {"running": 1, "recovering": 1, "fault": 1, "stopped": 1, "unknown": 1},
                "scene_state": "UNKNOWN",
                "qualified": False,
            },
        )

    def test_expiry_is_exclusive_and_snapshots_do_not_renew(self):
        fleet = FleetHealth(1)
        self.assertTrue(fleet.ingest(0, report(), now_ms=1000))
        self.assertEqual(fleet.snapshot(now_ms=2999)["states"]["running"], 1)
        self.assertEqual(fleet.snapshot(now_ms=3000)["states"]["unknown"], 1)
        self.assertEqual(fleet.snapshot(now_ms=3001)["states"]["unknown"], 1)

    def test_replay_and_out_of_order_reports_withdraw_previous_health(self):
        for raw in (report(), report(emitted=999, expires=2999)):
            with self.subTest(raw=raw):
                fleet = FleetHealth(1)
                self.assertTrue(fleet.ingest(0, report(), now_ms=1000))
                self.assertFalse(fleet.ingest(0, raw, now_ms=1001))
                self.assertEqual(fleet.snapshot(now_ms=1001)["states"]["unknown"], 1)
                self.assertTrue(fleet.ingest(0, report(emitted=1002), now_ms=1002))

    def test_invalid_input_preserves_replay_floor(self):
        fleet = FleetHealth(1)
        self.assertTrue(fleet.ingest(0, report(), now_ms=1000))
        self.assertFalse(fleet.ingest(0, b"invalid private data", now_ms=1001))
        self.assertFalse(fleet.ingest(0, report(), now_ms=1002))
        self.assertEqual(fleet.snapshot(now_ms=1002)["states"]["unknown"], 1)

    def test_expired_report_cannot_reappear_with_an_extended_lifetime(self):
        fleet = FleetHealth(1)
        self.assertTrue(fleet.ingest(0, report(expires=1001), now_ms=1000))
        self.assertEqual(fleet.snapshot(now_ms=1001)["states"]["unknown"], 1)
        self.assertFalse(fleet.ingest(0, report(expires=3000), now_ms=1001))
        self.assertEqual(fleet.snapshot(now_ms=1001)["states"]["unknown"], 1)

    def test_report_size_and_integer_time_boundaries(self):
        raw = report(emitted=0, expires=1)
        fleet = FleetHealth(1)
        self.assertTrue(fleet.ingest(0, raw.ljust(256), now_ms=0))
        self.assertFalse(fleet.ingest(0, raw.ljust(257), now_ms=0))
        last = 2**53 - 1
        self.assertTrue(fleet.ingest(0, report(emitted=last - 1, expires=last), now_ms=last - 1))
        self.assertEqual(fleet.snapshot(now_ms=last)["states"]["unknown"], 1)

    def test_real_supervisor_status_projects_without_starting_workers(self):
        from aethron_edge.runtime.supervisor import ApplianceSupervisor

        supervisor = ApplianceSupervisor()
        supervisor.config = SimpleNamespace(runtime_mode="appliance")
        fleet = FleetHealth(1)
        for now, state in ((1000, "running"), (1001, "fault")):
            if state == "fault":
                supervisor.faults.add("private-profile")
            status = supervisor.status(now * 1_000_000)
            raw = encode_local_health(status, now_ms=now)
            self.assertNotIn(b"private", raw)
            self.assertTrue(fleet.ingest(0, raw, now_ms=now))
            self.assertEqual(fleet.snapshot(now_ms=now)["states"][state], 1)

    def test_deterministic_hostile_bytes_fail_closed_without_exceptions(self):
        randomizer = random.Random(34)
        for size in range(257):
            raw = randomizer.randbytes(size)
            fleet = FleetHealth(1)
            self.assertTrue(fleet.ingest(0, report(), now_ms=1000))
            self.assertFalse(fleet.ingest(0, raw, now_ms=1001))
            self.assertEqual(fleet.snapshot(now_ms=1001)["states"]["unknown"], 1)

    def test_malformed_reports_clear_only_the_affected_slot(self):
        bad = [
            b"",
            b"null",
            b"[]",
            b"false",
            b"\xff",
            b"{" * 256,
            b" " * 257,
            report(location="private"),
            report().replace(b'"version": 1', b'"version": 1, "version": 1'),
            report().replace(b'"version": 1', b'"version": true'),
            report().replace(b'"version": 1', b'"version": 1.0'),
            report().replace(b'"version": 1', b'"version": 2'),
            report().replace(b'"emitted_ms": 1000', b'"emitted_ms": NaN'),
            report().replace(b'"emitted_ms": 1000', b'"emitted_ms": true'),
            report().replace(b'"emitted_ms": 1000', b'"emitted_ms": 1000.0'),
            report().replace(b'"status_expires_ms": 3000', b'"status_expires_ms": false'),
            report().replace(b'"status_expires_ms": 3000', b'"status_expires_ms": 3000.0'),
            report(state="private"),
            report(state=[]),
            report(state=None),
            report(emitted=-1),
            report(emitted=1002),
            report(expires=1001),
            report(expires=1000),
            report(expires=3001),
            report(expires=2**53),
            report().decode(),
            bytearray(report()),
            None,
        ]
        for raw in bad:
            with self.subTest(raw=raw):
                fleet = FleetHealth(2)
                for slot in (0, 1):
                    self.assertTrue(fleet.ingest(slot, report(), now_ms=1000))
                self.assertFalse(fleet.ingest(0, raw, now_ms=1001))
                states = fleet.snapshot(now_ms=1001)["states"]
                self.assertEqual((states["running"], states["unknown"]), (1, 1))

    def test_projection_rejects_invalid_or_stale_selected_fields_without_echo(self):
        for status in (
            None,
            {},
            json.loads(report(emitted=1001)),
            json.loads(report(expires=1000)),
        ):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "^invalid_health_report$"):
                    encode_local_health(status, now_ms=1000)

    def test_invalid_or_regressed_collector_clock_withdraws_all_and_keeps_floor(self):
        for now in (-1, True, 1000.0, None, 2**53, 999):
            with self.subTest(now=now):
                fleet = FleetHealth(2)
                for slot in (0, 1):
                    fleet.ingest(slot, report(), now_ms=1000)
                with self.assertRaisesRegex(ValueError, "^invalid_health_clock$"):
                    fleet.snapshot(now_ms=now)
                self.assertEqual(fleet.snapshot(now_ms=1000)["states"]["unknown"], 2)
                self.assertFalse(fleet.ingest(0, report(), now_ms=1000))
                with self.assertRaisesRegex(ValueError, "^invalid_health_clock$"):
                    fleet.ingest(0, report(emitted=999), now_ms=999)

    def test_invalid_slot_cannot_alias_authorized_slot(self):
        for slot in (-1, 1, True, 0.0, "0", None):
            with self.subTest(slot=slot):
                fleet = FleetHealth(1)
                fleet.ingest(0, report(), now_ms=1000)
                with self.assertRaisesRegex(ValueError, "^invalid_health_slot$"):
                    fleet.ingest(slot, report(emitted=1001), now_ms=1001)
                self.assertEqual(fleet.snapshot(now_ms=1001)["states"]["unknown"], 1)

    def test_capacity_and_empty_state_are_bounded(self):
        for count in (0, -1, 1025, True, 1.0, "1", None):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, "^invalid_health_capacity$"):
                    FleetHealth(count)
        self.assertEqual(FleetHealth(1024).snapshot(now_ms=0)["states"]["unknown"], 1024)

    def test_mutating_a_snapshot_cannot_change_collector_state(self):
        fleet = FleetHealth(1)
        fleet.ingest(0, report(), now_ms=1000)
        snapshot = fleet.snapshot(now_ms=1000)
        snapshot["states"]["running"] = 9000
        self.assertEqual(fleet.snapshot(now_ms=1000)["states"]["running"], 1)


if __name__ == "__main__":
    unittest.main()
