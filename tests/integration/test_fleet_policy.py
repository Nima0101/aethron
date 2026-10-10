"""Signed fleet configuration admission, without deployment or host operations."""

import base64
import hashlib
import json
import subprocess
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from aethron_edge.runtime.fleet_policy import load_fleet_policy
from aethron_edge.runtime.updates import verify_bundle


def policy(**changes):
    value = {
        "schema_version": 1,
        "bundle_version": 3,
        "not_before_unix_s": 1000,
        "expires_unix_s": 2000,
        "slot_count": 10,
        "batch_size": 2,
        "allow_initial_provisioning": False,
    }
    value.update(changes)
    return value


class FleetPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "test-only.pem"
        self.public = self.root / "test-only.pub"
        self.run_crypto("genpkey", "-algorithm", "ED25519", "-out", str(self.private))
        self.run_crypto("pkey", "-in", str(self.private), "-pubout", "-out", str(self.public))
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()

    def run_crypto(self, *args):
        subprocess.run(["openssl", *args], check=True, capture_output=True, timeout=5)

    def sign(self, value=None, *, raw=None, version=3, name="fleet-policy.json"):
        if raw is None:
            raw = json.dumps(policy() if value is None else value).encode()
        (self.bundle / name).write_bytes(raw)
        manifest = {
            "schema_version": 1,
            "version": version,
            "config_version": 1,
            "files": {name: hashlib.sha256(raw).hexdigest()},
        }
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        self.run_crypto(
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(self.private),
            "-in",
            str(self.bundle / "manifest.json"),
            "-out",
            str(self.bundle / "manifest.sig"),
        )

    def load(self, **changes):
        options = {"now_unix_s": 1000, "minimum_version": 3}
        options.update(changes)
        return load_fleet_policy(self.bundle, self.public, **options)

    def rejected(self, **changes):
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_policy$"):
            self.load(**changes)

    def test_verified_configuration_is_immutable_and_matches_signed_values(self):
        self.sign()
        value = self.load()
        self.assertEqual(value.bundle_version, 3)
        self.assertEqual(value.slot_count, 10)
        self.assertEqual(value.batch_size, 2)
        self.assertFalse(value.allow_initial_provisioning)
        self.assertEqual((value.not_before_unix_s, value.expires_unix_s), (1000, 2000))
        with self.assertRaises(FrozenInstanceError):
            value.batch_size = 20
        self.assertEqual(
            sorted(p.name for p in self.bundle.iterdir()),
            ["fleet-policy.json", "manifest.json", "manifest.sig"],
        )

    def test_valid_signature_does_not_override_time_or_durable_version_floor(self):
        self.sign()
        for changes in ({"now_unix_s": 999}, {"now_unix_s": 2000}, {"minimum_version": 4}):
            with self.subTest(changes=changes):
                self.rejected(**changes)
        self.assertEqual(self.load(now_unix_s=1999, minimum_version=1).bundle_version, 3)
        self.rejected(now_unix_s=2001)

    def test_bundle_and_policy_versions_must_agree(self):
        self.sign(policy(bundle_version=2))
        self.rejected(minimum_version=1)

    def test_unsigned_or_tampered_policy_never_loads(self):
        self.sign()
        (self.bundle / "fleet-policy.json").write_text(json.dumps(policy(batch_size=10)))
        self.rejected()

    def test_corrupt_signature_never_loads(self):
        self.sign()
        (self.bundle / "manifest.sig").write_bytes(bytes(64))
        self.rejected()

    def test_same_length_rsa_signature_cannot_select_a_different_algorithm(self):
        # Synthetic weak key only: demonstrates that 64 bytes do not imply Ed25519.
        self.run_crypto(
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:512",
            "-out",
            str(self.private),
        )
        self.run_crypto("pkey", "-in", str(self.private), "-pubout", "-out", str(self.public))
        self.sign()
        self.assertEqual((self.bundle / "manifest.sig").stat().st_size, 64)
        self.rejected()

    def test_verifier_uses_pinned_key_bytes_when_original_path_changes(self):
        self.sign()
        other_private = self.root / "other-key"
        other_public = self.root / "other-public"
        self.run_crypto("genpkey", "-algorithm", "ED25519", "-out", str(other_private))
        self.run_crypto("pkey", "-in", str(other_private), "-pubout", "-out", str(other_public))

        def replace_original_key(bundle, key):
            self.public.write_bytes(other_public.read_bytes())
            return verify_bundle(bundle, key)

        with patch("aethron_edge.runtime.fleet_policy.verify_bundle", replace_original_key):
            self.assertEqual(self.load().bundle_version, 3)

    def test_key_profile_rejects_malformed_or_ambiguous_input_before_verification(self):
        self.sign()
        valid = self.public.read_bytes()
        der = base64.b64decode(b"".join(valid.splitlines()[1:-1]))

        def pem(value):
            return (
                b"-----BEGIN PUBLIC KEY-----\n"
                + base64.b64encode(value)
                + b"\n-----END PUBLIC KEY-----\n"
            )

        encoded = base64.b64encode(der)
        alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        noncanonical = encoded[:-2] + bytes([alphabet[alphabet.index(encoded[-2]) + 1]]) + b"="
        cases = [
            b"",
            valid.replace(encoded, b"!" + encoded[1:]),
            valid.replace(encoded, noncanonical),
            valid + valid,
            b"comment\n" + valid,
            valid + b"comment\n",
            valid.ljust(1025),
            valid.replace(b"PUBLIC KEY", b"PRIVATE KEY"),
            pem(der[:8] + b"\x6e" + der[9:]),  # X25519 OID, not Ed25519.
            pem(der + b"\x00"),
            pem(der[:-1]),
            pem(bytes.fromhex("302c300706032b65700500032100") + der[12:]),
            pem(der[:11] + b"\x01" + der[12:]),  # Nonzero unused-bit count.
        ]
        for raw in cases:
            with self.subTest(size=len(raw)):
                self.public.write_bytes(raw)
                with patch("aethron_edge.runtime.fleet_policy.verify_bundle") as verifier:
                    self.rejected()
                    verifier.assert_not_called()

    def test_regular_key_file_required_and_pem_line_wrapping_is_preserved(self):
        self.sign()
        valid = self.public.read_bytes()
        lines = valid.splitlines()
        self.public.write_bytes(
            b"\r\n".join([lines[0], lines[1][:20], lines[1][20:], lines[2]]) + b"\r\n"
        )
        self.assertEqual(self.load().bundle_version, 3)
        self.public.unlink()
        target = self.root / "key-target"
        target.write_bytes(valid)
        self.public.symlink_to(target)
        self.rejected()

    def test_policy_must_be_a_signed_bundle_member(self):
        self.sign(name="other.json")
        self.rejected()

    def test_a_different_trust_root_never_loads(self):
        self.sign()
        other_private = self.root / "other-test-key"
        self.run_crypto("genpkey", "-algorithm", "ED25519", "-out", str(other_private))
        self.run_crypto("pkey", "-in", str(other_private), "-pubout", "-out", str(self.public))
        self.rejected()

    def test_replacement_after_bundle_verification_cannot_change_admitted_bytes(self):
        self.sign()

        def replace_after_verify(*args):
            manifest = verify_bundle(*args)
            (self.bundle / "fleet-policy.json").write_text(json.dumps(policy(batch_size=10)))
            return manifest

        with patch("aethron_edge.runtime.fleet_policy.verify_bundle", replace_after_verify):
            self.rejected()

    def test_link_substitution_after_verification_is_rejected(self):
        self.sign()

        def replace_after_verify(*args):
            manifest = verify_bundle(*args)
            path = self.bundle / "fleet-policy.json"
            external = self.root / "external-policy"
            path.rename(external)
            path.symlink_to(external)
            return manifest

        with patch("aethron_edge.runtime.fleet_policy.verify_bundle", replace_after_verify):
            self.rejected()

    def test_signed_invalid_schemas_and_privacy_fields_are_rejected(self):
        cases = [
            policy(location="private"),
            policy(device_id="private"),
            policy(raw_imagery=[]),
            policy(schema_version=True),
            policy(schema_version=2),
            policy(bundle_version=True),
            policy(bundle_version=3.0),
            policy(not_before_unix_s=True),
            policy(expires_unix_s=2000.0),
            policy(not_before_unix_s=-1),
            policy(expires_unix_s=2**53),
            policy(expires_unix_s=1000),
            policy(expires_unix_s=87401),
            policy(slot_count=True),
            policy(slot_count=0),
            policy(slot_count=1025),
            policy(batch_size=True),
            policy(batch_size=0),
            policy(batch_size=33),
            policy(batch_size=11),
            policy(allow_initial_provisioning=1),
            policy(allow_initial_provisioning="false"),
            policy(batch_size=[]),
        ]
        for value in cases:
            with self.subTest(value=value):
                self.sign(value)
                self.rejected()

    def test_strict_encoding_duplicates_and_byte_limit(self):
        valid = json.dumps(policy()).encode()
        cases = [
            b"\xff",
            b"null",
            b"[]",
            b"[" * 1000 + b"]" * 1000,
            valid.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1'),
            valid.replace(b'"batch_size": 2', b'"batch_size": NaN'),
            valid.decode().encode("utf-16"),
            valid.ljust(2049),
        ]
        for raw in cases:
            with self.subTest(raw=raw[:32]):
                self.sign(raw=raw)
                self.rejected()
        self.sign(raw=valid.ljust(2048))
        self.assertEqual(self.load().batch_size, 2)

    def test_clock_and_floor_must_be_strict_bounded_integers(self):
        self.sign()
        for field, values in (
            ("now_unix_s", (True, 1000.0, -1, 2**53, None)),
            ("minimum_version", (True, 3.0, 0, -1, 2**31, None)),
        ):
            for value in values:
                with self.subTest(field=field, value=value):
                    self.rejected(**{field: value})

    def test_maximum_valid_capacity_window_and_version(self):
        self.sign(
            policy(
                bundle_version=2**31 - 1,
                slot_count=1024,
                batch_size=32,
                expires_unix_s=87400,
                allow_initial_provisioning=True,
            ),
            version=2**31 - 1,
        )
        value = self.load(now_unix_s=87399)
        self.assertEqual((value.slot_count, value.batch_size), (1024, 32))
        self.assertTrue(value.allow_initial_provisioning)


if __name__ == "__main__":
    unittest.main()
