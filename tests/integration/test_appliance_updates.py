"""Offline signed updates must survive tamper, interruption and rollback attempts."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.runtime.updates import UpdateStore, verify_bundle


class Updates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = self.root / "test-only.pem"
        self.public = self.root / "test-only.pub"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(self.private)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(self.private), "-pubout", "-out", str(self.public)],
            check=True,
            capture_output=True,
        )
        self.store = UpdateStore(self.root / "installed", self.public)

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self, version, **changes):
        path = self.root / ("bundle-" + str(version))
        path.mkdir()
        data = b"verified offline content"
        (path / "model.bin").write_bytes(data)
        manifest = {
            "schema_version": 1,
            "version": version,
            "config_version": 1,
            "files": {"model.bin": hashlib.sha256(data).hexdigest()},
        }
        manifest.update(changes)
        (path / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(self.private),
                "-in",
                str(path / "manifest.json"),
                "-out",
                str(path / "manifest.sig"),
            ],
            check=True,
            capture_output=True,
        )
        return path

    def test_late_invalid_entry_is_rejected_before_payload_hashing_or_crypto(self):
        valid = hashlib.sha256(b"verified offline content").hexdigest()
        cases = [
            ("z/../escape", valid),
            ("z\ninvalid", valid),
            ("z" * 181, valid),
            ("z.bin", "a" * 63),
            ("z.bin", "A" * 64),
            ("z.bin", False),
            ("z.bin", 0),
            ("z.bin", []),
        ]
        for version, (name, expected) in enumerate(cases, 1):
            with self.subTest(name=name, expected=expected):
                bundle = self.bundle(version, files={"model.bin": valid, name: expected})
                with (
                    patch("aethron_edge.runtime.updates.digest", return_value=valid) as hashed,
                    patch(
                        "aethron_edge.runtime.updates.subprocess.run",
                        return_value=subprocess.CompletedProcess([], 0),
                    ) as crypto,
                ):
                    with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                        verify_bundle(bundle, self.public)
                hashed.assert_not_called()
                crypto.assert_not_called()

    def test_signature_verifies_the_parsed_manifest_not_a_reopened_replacement(self):
        bundle = self.bundle(1)
        path = bundle / "manifest.json"
        signed = path.read_bytes()
        forged = json.loads(signed)
        forged["version"] = 2
        path.write_text(json.dumps(forged, sort_keys=True))
        run = subprocess.run

        def restore_signed_file_before_openssl(command, **kwargs):
            path.write_bytes(signed)
            return run(command, **kwargs)

        with patch(
            "aethron_edge.runtime.updates.subprocess.run", restore_signed_file_before_openssl
        ):
            with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                verify_bundle(bundle, self.public)
        self.assertEqual(verify_bundle(bundle, self.public)["version"], 1)

    def test_signature_snapshot_is_private_and_removed_on_every_exit(self):
        run = subprocess.run
        for version, outcome in enumerate(("valid", "invalid", "timeout"), 1):
            with self.subTest(outcome=outcome):
                bundle = self.bundle(version)
                if outcome == "invalid":
                    (bundle / "manifest.sig").write_bytes(bytes(64))
                copies = []

                def inspect_snapshot(
                    command, *, bundle=bundle, copies=copies, outcome=outcome, **kwargs
                ):
                    manifest = Path(command[command.index("-in") + 1])
                    signature = Path(command[command.index("-sigfile") + 1])
                    self.assertNotEqual(manifest.parent, bundle)
                    self.assertEqual(signature.parent, manifest.parent)
                    self.assertEqual(manifest.read_bytes(), (bundle / "manifest.json").read_bytes())
                    self.assertEqual(signature.read_bytes(), (bundle / "manifest.sig").read_bytes())
                    if os.name != "nt":
                        self.assertEqual(manifest.parent.stat().st_mode & 0o777, 0o700)
                    copies.append(manifest.parent)
                    if outcome == "timeout":
                        raise subprocess.TimeoutExpired(command, 5)
                    return run(command, **kwargs)

                with patch("aethron_edge.runtime.updates.subprocess.run", inspect_snapshot):
                    if outcome == "valid":
                        self.assertEqual(verify_bundle(bundle, self.public)["version"], version)
                    else:
                        with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                            verify_bundle(bundle, self.public)
                self.assertEqual(len(copies), 1)
                self.assertFalse(copies[0].exists())

    def test_signature_growth_cannot_trigger_unbounded_read(self):
        from contextlib import contextmanager
        from types import SimpleNamespace

        bundle = self.bundle(1)
        signature = bundle / "manifest.sig"
        original_open = os.fdopen

        @contextmanager
        def grow_signature_after_inspection(fd, *args, **kwargs):
            is_signature = os.path.samestat(os.fstat(fd), signature.stat())
            if is_signature:
                with signature.open("r+b") as changing:
                    changing.truncate(10000)
            with original_open(fd, *args, **kwargs) as stream:
                if not is_signature:
                    yield stream
                else:

                    def bounded_read(size=-1):
                        self.assertGreaterEqual(size, 0)
                        self.assertLessEqual(size, 65)
                        return stream.read(size)

                    yield SimpleNamespace(read=bounded_read)

        with patch("os.fdopen", grow_signature_after_inspection):
            with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                verify_bundle(bundle, self.public)

    def test_integrity_trace_stops_at_failed_stage_without_disclosing_paths(self):
        stages = [
            "bundle_signature_start",
            "bundle_signature_done",
            "bundle_hashes_done",
            "bundle_inventory_done",
        ]
        script = """from pathlib import Path
import sys
from aethron_edge.runtime.updates import verify_bundle
try:
    verify_bundle(Path(sys.argv[1]), Path(sys.argv[2]))
except ValueError:
    raise SystemExit(2)
"""
        for version, kind, count in (
            (1, "valid", 4),
            (2, "signature", 1),
            (3, "hash", 2),
            (4, "inventory", 3),
        ):
            with self.subTest(kind=kind):
                bundle = self.bundle(version)
                if kind == "signature":
                    (bundle / "manifest.sig").write_bytes(bytes(64))
                elif kind == "hash":
                    (bundle / "model.bin").write_bytes(b"tampered-private-value")
                elif kind == "inventory":
                    (bundle / "unsigned-private-file").write_bytes(b"private")
                result = subprocess.run(
                    [sys.executable, "-I", "-B", "-c", script, str(bundle), str(self.public)],
                    env=dict(os.environ, AETHRON_STARTUP_TRACE="1"),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(result.returncode, 0 if kind == "valid" else 2)
                self.assertEqual(result.stdout, "")
                rows = [line.split() for line in result.stderr.splitlines()]
                self.assertEqual([row[1] for row in rows], stages[:count])
                for row in rows:
                    self.assertEqual(row[0], "AETHRON_STARTUP")
                    self.assertEqual(len(row), 3)
                    self.assertGreaterEqual(int(row[2]), 0)
                self.assertNotIn(str(bundle), result.stderr)
                self.assertNotIn("private", result.stderr)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX file types")
    def test_manifest_and_signature_substitution_is_rejected_at_open(self):
        original_open = os.open
        for version, name in enumerate(("manifest.json", "manifest.sig"), 1):
            for kind in ("symlink", "fifo"):
                with self.subTest(name=name, kind=kind):
                    bundle = self.bundle(version * 10 + (kind == "fifo"))
                    path = bundle / name
                    swaps, descriptors = [], []

                    def swap_at_open(
                        candidate,
                        flags,
                        *args,
                        path=path,
                        kind=kind,
                        swaps=swaps,
                        descriptors=descriptors,
                        **kwargs,
                    ):
                        if Path(candidate) == path:
                            self.assertTrue(flags & os.O_NONBLOCK)
                            self.assertTrue(flags & os.O_NOFOLLOW)
                            old = path.with_suffix(".old")
                            path.rename(old)
                            if kind == "fifo":
                                os.mkfifo(path)
                            else:
                                path.symlink_to(old)
                            swaps.append(True)
                            fd = original_open(candidate, flags, *args, **kwargs)
                            descriptors.append(fd)
                            return fd
                        return original_open(candidate, flags, *args, **kwargs)

                    with patch("os.open", swap_at_open):
                        with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                            verify_bundle(bundle, self.public)
                    self.assertEqual(swaps, [True])
                    for fd in descriptors:
                        with self.assertRaises(OSError):
                            os.fstat(fd)

    def test_oversized_manifest_is_rejected_before_reading(self):
        bundle = self.bundle(1)
        with (bundle / "manifest.json").open("r+b") as stream:
            stream.truncate(2 * 1024 * 1024 + 1)
        with patch("os.open", side_effect=AssertionError("manifest read attempted")):
            with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                verify_bundle(bundle, self.public)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_nonregular_manifest_is_rejected_before_opening(self):
        bundle = self.bundle(1)
        path = bundle / "manifest.json"
        path.unlink()
        os.mkfifo(path)
        # Trap opening the FIFO so the regression cannot hang the test runner.
        with patch("os.open", side_effect=AssertionError("FIFO open attempted")):
            with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                verify_bundle(bundle, self.public)

    def test_manifest_growth_cannot_trigger_unbounded_read(self):
        from contextlib import contextmanager
        from types import SimpleNamespace

        bundle = self.bundle(1)
        manifest = bundle / "manifest.json"
        original_open = os.fdopen

        @contextmanager
        def grow_after_inspection(fd, *args, **kwargs):
            with manifest.open("r+b") as changing:
                changing.truncate(2 * 1024 * 1024 + 100)
            with original_open(fd, *args, **kwargs) as stream:

                def bounded_read(size=-1):
                    self.assertGreaterEqual(size, 0)
                    self.assertLessEqual(size, 2 * 1024 * 1024 + 1)
                    return stream.read(size)

                yield SimpleNamespace(read=bounded_read)

        self.assertLess(manifest.stat().st_size, 2 * 1024 * 1024)
        with patch("os.fdopen", grow_after_inspection):
            with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                verify_bundle(bundle, self.public)

    def test_missing_control_state_allows_initial_activation(self):
        self.assertEqual(self.store.recover(), {"state": "unprovisioned"})
        candidate = self.store.stage_update(self.bundle(1))
        self.store.activate(candidate)
        self.assertEqual(self.store.recover()["version"], 1)

    def test_oversized_control_state_is_rejected_before_reading(self):
        path = self.store.root / "active.json"
        with path.open("wb") as stream:
            stream.truncate(65537)
        with patch("os.open", side_effect=AssertionError("state read attempted")):
            self.assertEqual(self.store.recover(), {"state": "fault"})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_nonregular_control_state_is_rejected_before_opening(self):
        os.mkfifo(self.store.root / "active.json")
        with patch("os.open", side_effect=AssertionError("FIFO open attempted")):
            self.assertEqual(self.store.recover(), {"state": "fault"})

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_control_state_links_cannot_provision_or_activate(self):
        candidate = self.store.stage_update(self.bundle(1))
        target = self.root / "external-state"
        path = self.store.root / "active.json"
        for present in (False, True):
            with self.subTest(present=present):
                if present:
                    target.write_text(
                        json.dumps({"slot": candidate.path.name, "minimum_version": 1})
                    )
                path.symlink_to(target)
                try:
                    self.assertEqual(self.store.recover(), {"state": "fault"})
                    with self.assertRaises(ValueError):
                        self.store.activate(candidate)
                    self.assertTrue(path.is_symlink())
                finally:
                    path.unlink()

    def test_control_state_growth_cannot_trigger_unbounded_read(self):
        from contextlib import contextmanager
        from types import SimpleNamespace

        path = self.store.root / "active.json"
        path.write_text("{}")
        original_open = os.fdopen

        @contextmanager
        def grow_after_inspection(fd, *args, **kwargs):
            with path.open("r+b") as changing:
                changing.truncate(65636)
            with original_open(fd, *args, **kwargs) as stream:

                def bounded_read(size=-1):
                    self.assertGreaterEqual(size, 0)
                    self.assertLessEqual(size, 65537)
                    return stream.read(size)

                yield SimpleNamespace(read=bounded_read)

        with patch("os.fdopen", grow_after_inspection):
            self.assertEqual(self.store.recover(), {"state": "fault"})

    def test_invalid_control_state_cannot_reset_rollback_floor(self):
        candidate = self.store.stage_update(self.bundle(1))
        path = self.store.root / "active.json"
        slot = candidate.path.name
        invalid = ["null", "{}", "[]", "false", "0", "[" * 2000 + "]" * 2000]
        invalid += [
            json.dumps({"slot": slot, "minimum_version": value})
            for value in (True, False, 0, -1, 2**31, 1.0, "1", None)
        ]
        invalid += [
            json.dumps({"slot": value, "minimum_version": 1})
            for value in (None, [], 1, "../outside", "1-deadbeef")
        ]
        invalid += [json.dumps({"slot": slot, "minimum_version": 1, "extra": True})]
        for raw in invalid:
            with self.subTest(raw=raw[:100]):
                path.write_text(raw)
                self.assertEqual(self.store.recover(), {"state": "fault"})
                with self.assertRaises(ValueError):
                    self.store.activate(candidate)
                self.assertEqual(path.read_text(), raw)
                self.assertFalse((self.store.root / "active.pending").exists())

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_activation_does_not_follow_abandoned_pending_link(self):
        candidate = self.store.stage_update(self.bundle(1))
        outside = self.root / "unrelated-private-data"
        outside.write_bytes(b"must remain unchanged")
        pending = self.store.root / "active.pending"
        pending.symlink_to(outside)
        self.store.activate(candidate)
        self.assertEqual(outside.read_bytes(), b"must remain unchanged")
        self.assertTrue(pending.is_symlink())
        self.assertEqual(self.store.recover()["version"], 1)
        self.assertEqual((self.store.root / "active.json").stat().st_mode & 0o777, 0o600)

    def test_interrupted_activation_keeps_previous_state_and_removes_scratch(self):
        one = self.store.stage_update(self.bundle(1))
        two = self.store.stage_update(self.bundle(2))
        self.store.activate(one)
        previous = (self.store.root / "active.json").read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("simulated interrupted replace")):
            with self.assertRaises(OSError):
                self.store.activate(two)
        self.assertEqual((self.store.root / "active.json").read_bytes(), previous)
        self.assertEqual(self.store.recover()["version"], 1)
        self.assertEqual(list(self.store.root.glob("*.pending")), [])
        self.store.activate(two)
        self.assertEqual(self.store.recover()["version"], 2)
        with self.assertRaisesRegex(ValueError, "rollback_rejected"):
            self.store.activate(one)

    def test_overlapping_process_activation_cannot_lower_rollback_floor(self):
        one = self.store.stage_update(self.bundle(1))
        two = self.store.stage_update(self.bundle(2))
        marker = self.root / "state-read"
        script = """import sys
from pathlib import Path
from aethron_edge.runtime.updates import UpdateStore, VerifiedCandidate
store = UpdateStore(Path(sys.argv[1]), Path(sys.argv[2]))
original = store._state
def pause_after_read():
    state = original()
    Path(sys.argv[4]).touch()
    if sys.stdin.readline().strip() != 'continue':
        raise RuntimeError('test_interrupted')
    return state
store._state = pause_after_read
store.activate(VerifiedCandidate(Path(sys.argv[3]), 1))
"""
        with subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                script,
                str(self.store.root),
                str(self.public),
                str(one.path),
                str(marker),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as child:
            try:
                deadline = time.monotonic() + 20
                while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists(), "activation did not reach state read")
                three = self.bundle(3)
                for operation in (
                    lambda: self.store.activate(two),
                    lambda: self.store.stage_update(three),
                    self.store.factory_reset,
                ):
                    with self.assertRaisesRegex(ValueError, "update_store_busy"):
                        operation()
                self.assertEqual(self.store.recover(), {"state": "unprovisioned"})
            finally:
                stdout, stderr = child.communicate("continue\n", timeout=20)
        self.assertEqual(child.returncode, 0, stderr)
        self.assertEqual(stdout, "")
        self.store.activate(two)
        with self.assertRaisesRegex(ValueError, "rollback_rejected"):
            self.store.activate(one)
        self.assertEqual(self.store.recover()["version"], 2)

    def test_process_exit_does_not_leave_a_stale_activation_lock(self):
        candidate = self.store.stage_update(self.bundle(1))
        script = """import os, sys
from pathlib import Path
from aethron_edge.runtime.updates import UpdateStore, VerifiedCandidate
store = UpdateStore(Path(sys.argv[1]), Path(sys.argv[2]))
store._state = lambda: os._exit(0)
store.activate(VerifiedCandidate(Path(sys.argv[3]), 1))
raise SystemExit(2)
"""
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                script,
                str(self.store.root),
                str(self.public),
                str(candidate.path),
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.store.recover(), {"state": "unprovisioned"})
        self.store.activate(candidate)
        self.assertEqual(self.store.recover()["version"], 1)

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_update_lock_rejects_symlink_without_writing_target(self):
        candidate = self.store.stage_update(self.bundle(1))
        lock = self.store.root / ".mutation.lock"
        lock.unlink(missing_ok=True)
        outside = self.root / "unrelated-lock-data"
        outside.write_bytes(b"preserve")
        lock.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "invalid_update_lock"):
            self.store.activate(candidate)
        self.assertEqual(outside.read_bytes(), b"preserve")
        self.assertFalse((self.store.root / "active.json").exists())

    def test_factory_reset_retains_lock_inode(self):
        candidate = self.store.stage_update(self.bundle(1))
        self.store.activate(candidate)
        lock = self.store.root / ".mutation.lock"
        before = lock.stat()
        self.store.factory_reset()
        self.assertTrue(os.path.samestat(before, lock.stat()))
        self.assertEqual(self.store.recover(), {"state": "unprovisioned"})
        self.store.activate(self.store.stage_update(self.bundle(2)))
        self.assertEqual(self.store.recover()["version"], 2)

    def test_activate_recover_tamper_and_rollback(self):
        one = self.store.stage_update(self.bundle(1))
        self.store.activate(one)
        self.assertEqual(self.store.recover()["version"], 1)
        two = self.store.stage_update(self.bundle(2))
        self.store.activate(two)
        with self.assertRaises(ValueError):
            self.store.activate(one)
        (two.path / "model.bin").write_bytes(b"corrupted")
        self.assertEqual(
            self.store.recover()["state"], "fault"
        )  # revoked older slot cannot recover

    def test_bad_signature_missing_model_incompatible_and_interrupted_stage(self):
        active = self.store.stage_update(self.bundle(1))
        self.store.activate(active)
        broken = self.bundle(2)
        (broken / "manifest.sig").write_bytes(b"bad")
        with self.assertRaises(ValueError):
            self.store.stage_update(broken)
        missing = self.bundle(3)
        (missing / "model.bin").unlink()
        with self.assertRaises(ValueError):
            self.store.stage_update(missing)
        with self.assertRaises(ValueError):
            self.store.stage_update(self.bundle(4, config_version=2))
        (self.root / "installed" / "interrupted.pending").mkdir()
        self.assertEqual(self.store.recover()["version"], 1)

    def test_appliance_config_must_be_in_verified_bundle(self):
        from types import SimpleNamespace

        from aethron_edge.runtime.updates import verify_configuration

        bundle = self.bundle(1)
        config = SimpleNamespace(
            integrity_bundle=str(bundle), trust_root=str(self.public), profiles=[], telemetry=[]
        )
        self.assertEqual(verify_configuration(config, bundle / "model.bin")["version"], 1)
        outside = self.root / "external-config.json"
        outside.write_text("{}")
        with self.assertRaises(ValueError):
            verify_configuration(config, outside)

    def test_offline_boot_slot_selection_and_corrupt_active_fault(self):
        from aethron_edge.runtime.updates import selected_runtime

        self.assertIsNone(selected_runtime(self.store.root, self.public))
        bundle = self.bundle(1)
        self.store.activate(self.store.stage_update(bundle))
        # A valid signed data bundle is insufficient: runtime entry/config required.
        with self.assertRaises(ValueError):
            selected_runtime(self.store.root, self.public)
        (self.store.root / "active.json").write_text("bad")
        with self.assertRaises(ValueError):
            selected_runtime(self.store.root, self.public)

    def test_excessive_manifest_nesting_is_rejected_before_crypto(self):
        bundle = self.bundle(1)
        (bundle / "manifest.json").write_bytes(b"[" * 10000 + b"0" + b"]" * 10000)
        with patch(
            "aethron_edge.runtime.updates.subprocess.run", side_effect=AssertionError("crypto")
        ):
            for operation in (
                lambda: verify_bundle(bundle, self.public),
                lambda: self.store.stage_update(bundle),
            ):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                        operation()

    def test_excessive_active_manifest_nesting_recovers_as_fault(self):
        candidate = self.store.stage_update(self.bundle(1))
        self.store.activate(candidate)
        (candidate.path / "manifest.json").write_bytes(b"[" * 10000 + b"0" + b"]" * 10000)
        self.assertEqual(self.store.recover(), {"state": "fault"})

    def test_boolean_manifest_version_rejected(self):
        with self.assertRaises(ValueError):
            self.store.stage_update(self.bundle(1, schema_version=True))

    def test_symlink_escape_and_factory_reset(self):
        path = self.bundle(1)
        (path / "model.bin").unlink()
        (path / "model.bin").symlink_to(self.public)
        with self.assertRaises(ValueError):
            self.store.stage_update(path)
        path = self.bundle(2)
        self.store.activate(self.store.stage_update(path))
        self.store.factory_reset()
        self.assertEqual(self.store.recover()["state"], "unprovisioned")

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_unsigned_directory_and_dangling_links_are_rejected(self):
        for version, target in ((1, self.root), (2, self.root / "missing")):
            with self.subTest(version=version):
                bundle = self.bundle(version)
                (bundle / "unsigned-alias").symlink_to(target, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                    verify_bundle(bundle, self.public)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_unsigned_special_file_is_rejected_without_reading_it(self):
        bundle = self.bundle(1)
        os.mkfifo(bundle / "unsigned-pipe")
        with self.assertRaisesRegex(ValueError, "invalid_bundle"):
            verify_bundle(bundle, self.public)

    def test_unreadable_inventory_directory_cannot_be_silently_skipped(self):
        bundle = self.bundle(1)
        inaccessible = bundle / "unreadable"
        inaccessible.mkdir()
        scandir = os.scandir

        def denied(path):
            if os.fspath(path) == str(inaccessible):
                raise PermissionError("test-only directory permission denial")
            return scandir(path)

        with patch("os.scandir", side_effect=denied):
            with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                verify_bundle(bundle, self.public)

    def test_nested_inventory_verifies_every_hash(self):
        bundle = self.bundle(1)
        nested = bundle / "runtime" / "lib" / "module.bin"
        nested.parent.mkdir(parents=True)
        (bundle / "model.bin").rename(nested)
        manifest = json.loads((bundle / "manifest.json").read_text())
        manifest["files"] = {
            "runtime/lib/module.bin": manifest["files"]["model.bin"],
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(self.private),
                "-in",
                str(bundle / "manifest.json"),
                "-out",
                str(bundle / "manifest.sig"),
            ],
            check=True,
            capture_output=True,
        )
        self.assertEqual(verify_bundle(bundle, self.public), manifest)
        nested.write_bytes(b"untrusted replacement")
        with self.assertRaisesRegex(ValueError, "invalid_bundle"):
            verify_bundle(bundle, self.public)

    @unittest.skipIf(os.name == "nt", "requires local symlink permission")
    def test_signed_parent_link_cannot_substitute_identical_contents(self):
        bundle = self.bundle(1)
        outside = self.root / "outside"
        outside.mkdir()
        (bundle / "model.bin").rename(outside / "model.bin")
        (bundle / "runtime").symlink_to(outside, target_is_directory=True)
        manifest = json.loads((bundle / "manifest.json").read_text())
        manifest["files"] = {"runtime/model.bin": manifest["files"]["model.bin"]}
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(self.private),
                "-in",
                str(bundle / "manifest.json"),
                "-out",
                str(bundle / "manifest.sig"),
            ],
            check=True,
            capture_output=True,
        )
        with self.assertRaisesRegex(ValueError, "invalid_bundle"):
            verify_bundle(bundle, self.public)
