"""Per-supervisor-boot ROS clock authority: software clock, never exposure proof."""

import importlib.util
import json
import unittest

from aethron_edge.sensors.ros2 import RosIngress


class RosAuthority(unittest.TestCase):
    def setUp(self):
        from test_sensor_provider import SensorProvider

        fixture = SensorProvider()
        fixture.setUp()
        self.calibration = fixture.config()
        self.now = 10_000_000_000
        self.wall_offset = 1_800_000_000_000_000_000

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.sensors.ros_authority"))
        from aethron_edge.sensors import ros_authority

        return ros_authority

    def manifest(self, **changes):
        values = {
            "version": 1,
            "mode": "ros",
            "timestamp_authority": "same_host_system_software",
            "calibration": self.calibration.model_dump(),
            "indices": [[1, 1]],
            "valid_for_ns": 500_000_000,
            "timestamp_error_ns": 1_000_000,
            "clock_drift_budget_ns": 1_000_000,
            "topic": "/aethron/depth",
            "camera_info_topic": "/aethron/camera_info",
            "domain_id": 73,
            "meters_per_unit": 0.001,
        }
        values.update(changes)
        return self.api().load_ros_manifest(json.dumps(values).encode())

    def grant(self, manifest=None):
        return self.api().issue_boot_grant(
            manifest or self.manifest(),
            monotonic=lambda: self.now,
            realtime=lambda: self.now + self.wall_offset,
        )

    def guard(self, grant=None, manifest=None, **changes):
        manifest = manifest or self.manifest()
        grant = grant or self.grant(manifest)
        fields = {
            "boot_id": grant.boot_id,
            "monotonic": lambda: self.now,
            "realtime": lambda: self.now + self.wall_offset,
        }
        fields.update(changes)
        return self.api().ClockGuard(grant, manifest, **fields)

    def test_strict_manifest_no_implicit_clock_or_foreign_calibration(self):
        m = self.manifest()
        self.assertEqual(m.indices, ((1, 1),))
        mutations = [
            {"timestamp_authority": "hardware_exposure"},
            {"timestamp_authority": "ros_simulation"},
            {"timestamp_authority": "remote_ntp"},
            {"valid_for_ns": True},
            {"valid_for_ns": 600_000_000_001},
            {"timestamp_error_ns": 50_000_000},
            {"clock_drift_budget_ns": 50_000_000},
            {"indices": [[1, 1], [1, 1]]},
            {"indices": [[10, 0]]},
            {"meters_per_unit": None},
            {"topic": "relative"},
            {"camera_info_topic": None},
            {"camera_info_topic": "/aethron/depth"},
            {"domain_id": 233},
            {"live_evidence": True},
        ]
        for changes in mutations:
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, "invalid_ros_manifest"),
            ):
                self.manifest(**changes)
        raw = m.model_dump_json()
        for data in (
            raw.replace('"version":1', '"version":1,"version":1').encode(),
            b" " * 65537,
            b"[" * 1000,
        ):
            with self.assertRaisesRegex(ValueError, "invalid_ros_manifest"):
                self.api().load_ros_manifest(data)

    def test_boot_and_manifest_binding_expiry_and_worker_restart_do_not_renew(self):
        m = self.manifest()
        grant = self.grant(m)
        self.assertNotEqual(grant.boot_id, self.grant(m).boot_id)
        with self.assertRaisesRegex(ValueError, "invalid_clock_authority"):
            self.guard(grant, boot_id="wrong_boot")
        with self.assertRaisesRegex(ValueError, "invalid_clock_authority"):
            self.guard(grant, self.manifest(topic="/changed"))
        first = self.guard(grant)
        self.now += 100_000_000
        replacement = self.guard(grant)
        self.assertEqual(first.mapping.valid_until_ns, replacement.mapping.valid_until_ns)
        self.assertEqual(replacement.mapping.offset_ns, -self.wall_offset)
        self.assertFalse(replacement.live_evidence)
        self.now = grant.valid_until_ns + 1
        self.assertFalse(replacement.check())
        self.now -= 2
        self.assertFalse(replacement.check(), "expired guard cannot revive")
        self.now = grant.valid_until_ns + 1
        with self.assertRaisesRegex(ValueError, "invalid_clock_authority"):
            self.guard(grant)

    def test_wall_step_and_monotonic_rewind_revoke_permanently(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                guard = self.guard()
                self.wall_offset += direction * 2_000_001
                self.assertFalse(guard.check())
                self.assertEqual(guard.fault, "clock_drift")
                self.wall_offset -= direction * 2_000_001
                self.assertFalse(guard.check())
        guard = self.guard()
        self.now -= 1
        self.assertFalse(guard.check())
        self.assertEqual(guard.fault, "clock_rewind")

    def test_captured_guest_clock_steps_revoke_without_remapping(self):
        # preflight-ros/signed-raw.log: two observed samples from a failed CLI run.
        # Rebased times preserve the numeric deltas without retaining host stamps.
        from dataclasses import replace

        for delta, duration in ((-7_418_465, 1000), (-7_418_215, 500)):
            with self.subTest(delta_ns=delta):
                manifest = self.manifest()
                grant = replace(self.grant(manifest), sample_error_ns=688)
                guard = self.guard(grant, manifest)
                mapping = guard.mapping
                bridge = RosIngress(
                    modality="depth", frame_id="front_optical", meters_per_unit=0.001
                )
                bridge.bind_clock(mapping)
                before = self.now + 20_404_041
                ticks = iter((before, before + duration))
                guard.monotonic = lambda ticks=ticks: next(ticks)
                wall = before + duration // 2 - grant.offset_ns - delta
                guard.realtime = lambda wall=wall: wall
                self.assertFalse(guard.check(ingress=bridge))
                self.assertEqual(guard.fault, "clock_drift")
                self.assertIsNone(bridge.mapping)
                self.assertIsNone(bridge.latest)
                self.assertEqual(guard.mapping, mapping)
                self.assertEqual(guard.grant, grant)
                # Restoring the original relation cannot revive either grant.
                guard.monotonic = lambda now=before + duration: now
                guard.realtime = lambda wall=before + duration - grant.offset_ns: wall
                self.assertFalse(guard.check(ingress=bridge))
                self.assertEqual(guard.fault, "clock_drift")
                self.assertFalse(guard.live_evidence)

    def test_sampling_delay_malformed_time_and_drift_budget_are_bounded(self):
        m = self.manifest()
        ticks = iter([self.now, self.now + 1_000_001])
        with self.assertRaisesRegex(ValueError, "invalid_clock_authority"):
            self.api().issue_boot_grant(m, monotonic=lambda: next(ticks), realtime=lambda: 100)
        for value in (True, -1, 2**63, float("nan")):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "invalid_clock_authority"),
            ):
                self.api().issue_boot_grant(
                    m, monotonic=lambda value=value: value, realtime=lambda: 100
                )
        guard = self.guard()
        self.wall_offset += 500_000
        self.assertTrue(guard.check())
        self.assertEqual(guard.mapping.uncertainty_ns, 2_000_000)
        self.assertFalse(guard.live_evidence)

    def test_authority_revocation_clears_ingress_and_provider(self):
        from aethron_edge.sensors.provider import GeometryProvider

        manifest = self.manifest()
        guard = self.guard(manifest=manifest)
        b = RosIngress(modality="depth", frame_id="depth_optical", meters_per_unit=0.001)
        provider = GeometryProvider(
            manifest.calibration,
            mode="ros",
            clock_id=guard.boot_id,
            valid_for_ns=manifest.valid_for_ns,
            clock=lambda: self.now,
        )
        b.bind_clock(guard.mapping)
        self.assertTrue(guard.check(ingress=b, provider=provider))
        self.now += manifest.valid_for_ns + 1
        self.assertFalse(guard.check(ingress=b, provider=provider))
        self.assertIsNone(b.mapping)
        self.assertIsNone(b.latest)
        self.assertTrue(provider.binding.closed)
        self.assertFalse(provider.status()["geometry_available"])

    def test_renewal_requires_versioned_synthetic_opt_in(self):
        for changes in (
            {"version": 1, "renewal": "software_fixture"},
            {"version": 2, "renewal": "physical_mount"},
            {
                "version": 2,
                "renewal": "software_fixture",
                "calibration": {
                    **self.calibration.model_dump(),
                    "rig": {**self.calibration.rig.model_dump(), "evidence": "external_unverified"},
                },
            },
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manifest(**changes)
        self.assertEqual(self.manifest().renewal, "disabled")
        m = self.manifest(version=2, renewal="software_fixture")
        self.assertFalse(self.guard(manifest=m).live_evidence)

    def test_renewal_keeps_original_anchor_and_requires_fresh_geometry(self):
        m = self.manifest(version=2, renewal="software_fixture")
        guard = self.guard(manifest=m)
        original = guard.grant
        self.now += 250_000_000
        self.wall_offset += 400_000
        grant = guard.renew(m, emitted_ns=self.now - 10, expires_ns=self.now + 10_000_000)
        self.assertEqual(grant.valid_until_ns, 10_750_000_000)
        self.assertEqual(grant.issued_ns, 10_250_000_000)
        self.assertEqual(grant.generation, 1)
        self.assertEqual(grant.boot_id, original.boot_id)
        self.assertEqual(grant.offset_ns, original.offset_ns)
        self.now += 250_000_000
        self.wall_offset += 700_000  # Incremental drift must not reset at each renewal.
        with self.assertRaises(ValueError):
            guard.renew(m, emitted_ns=self.now, expires_ns=self.now + 10_000_000)
        self.wall_offset -= 1_100_000
        self.assertFalse(guard.check())

    def test_failed_revalidation_cannot_revive_or_extend(self):
        m = self.manifest(version=2, renewal="software_fixture")
        for mode in ("expired", "stale", "future", "changed", "early", "disabled", "closed"):
            with self.subTest(mode=mode):
                self.now = 10_000_000_000
                current = self.manifest() if mode == "disabled" else m
                guard = self.guard(manifest=current)
                original = guard.grant
                self.now += 100 if mode == "early" else 250_000_000
                emitted, expires = self.now, self.now + 10_000_000
                if mode == "expired":
                    self.now = original.valid_until_ns + 1
                if mode == "stale":
                    expires = self.now - 1
                if mode == "future":
                    emitted = self.now + 1
                if mode == "changed":
                    current = self.manifest(version=2, renewal="software_fixture", domain_id=74)
                if mode == "closed":
                    guard.close()
                with self.assertRaises(ValueError):
                    guard.renew(current, emitted_ns=emitted, expires_ns=expires)
                self.assertEqual(guard.grant, original)
                self.assertFalse(guard.check())

    def test_worker_accepts_only_sequential_authority_and_clears_old_geometry(self):
        from dataclasses import replace

        from aethron_edge.sensors.provider import GeometryProvider

        m = self.manifest(version=2, renewal="software_fixture")
        parent = self.guard(manifest=m)
        worker = self.guard(parent.grant, m)
        bridge = RosIngress(modality="depth", frame_id="depth_optical", meters_per_unit=0.001)
        bridge.bind_clock(worker.mapping)
        bridge.last_stamp = 123
        bridge.calibration = (m.calibration.source_camera, "fixture", self.now + 400_000_000)
        provider = GeometryProvider(
            m.calibration,
            mode="ros",
            clock_id=parent.boot_id,
            valid_for_ns=m.valid_for_ns,
            clock=lambda: self.now,
        )
        self.now += 250_000_000
        grant = parent.renew(m, emitted_ns=self.now, expires_ns=self.now + 10_000_000)
        worker.accept_renewal(grant, m, ingress=bridge, provider=provider)
        self.assertTrue(provider.binding.closed)
        self.assertIsNone(bridge.latest)
        self.assertIsNone(bridge.calibration)
        self.assertIsNone(bridge.mapping)
        self.assertTrue(bridge.pending_break)
        self.assertEqual(bridge.last_stamp, 123, "epoch switch cannot admit replayed source stamps")
        self.assertEqual(worker.mapping.valid_until_ns, 10_750_000_000)
        self.now += 250_000_000
        second = parent.renew(m, emitted_ns=self.now, expires_ns=self.now + 10_000_000)
        for change in (
            {"generation": 1},
            {"generation": 3},
            {"generation": True},
            {"boot_id": "other_boot"},
            {"manifest_digest": "0" * 64},
            {"offset_ns": 0},
            {"sample_error_ns": 5},
            {"valid_until_ns": 2**63 - 1},
            {"issued_ns": self.now + 1},
        ):
            with self.subTest(change=change):
                fresh = self.guard(grant, m)
                with self.assertRaises(ValueError):
                    fresh.accept_renewal(replace(second, **change), m)
                self.assertFalse(fresh.check())
        self.now = grant.valid_until_ns + 1
        with self.assertRaises(ValueError):
            worker.accept_renewal(second, m, ingress=bridge, provider=provider)
        self.assertFalse(worker.check())
