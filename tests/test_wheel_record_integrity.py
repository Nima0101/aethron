"""Declared wheel RECORD hashes and sizes must describe the archive bytes."""

import base64
import csv
import hashlib
import io
import unittest

from test_wheel_record_ownership import record_wheel

from scripts import package_check


def declared_record(path, digest="", size=""):
    output = io.StringIO(newline="")
    csv.writer(output).writerow((path, digest, size))
    return output.getvalue()


def encoded_digest(data, algorithm="sha256"):
    return (
        algorithm
        + "="
        + base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


class WheelRecordIntegrity(unittest.TestCase):
    def test_declared_hash_and_size_match_sources_and_resources(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for data in (b"", b"resource\x00\xff" * 20000):
                    path = f"{package}/resources/caf\u00e9,notes.txt"
                    for algorithm in ("sha256", "sha384", "sha512", "sha3_256", "blake2b"):
                        with self.subTest(package=package, layout=layout, algorithm=algorithm):
                            raw, payload = record_wheel(
                                package,
                                declared_record(
                                    path, encoded_digest(data, algorithm), str(len(data))
                                ),
                                layout,
                                extras={path: data},
                                complete=True,
                            )
                            package_check.validate_source_payload(raw, payload, package)

    def test_false_hash_and_size_reject_even_when_package_sources_match(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for path, data in (
                    (f"{package}/module.py", b"VALUE = 1\n"),
                    (f"{package}/notes.txt", b"archive resource"),
                ):
                    for digest, size in (
                        (encoded_digest(b"different"), str(len(data))),
                        (encoded_digest(data), str(len(data) + 1)),
                        ("", str(len(data) + 1)),
                        (encoded_digest(b"different"), ""),
                    ):
                        with self.subTest(package=package, layout=layout, path=path, size=size):
                            extras = {} if path.endswith(".py") else {path: data}
                            raw, payload = record_wheel(
                                package,
                                declared_record(path, digest, size),
                                layout,
                                extras,
                                complete=True,
                            )
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(raw, payload, package)

    def test_invalid_digest_or_size_has_fixed_error(self):
        data = b"VALUE = 1\n"
        for digest, size in (
            ("private-fixture-token", ""),
            ("sha256=", ""),
            (encoded_digest(data) + "=", ""),
            ("sha256=" + "!" * 43, ""),
            ("md5=ignored", ""),
            ("sha1=ignored", ""),
            ("shake_256=ignored", ""),
            ("unknown=ignored", ""),
            ("", "-1"),
            ("", "+10"),
            ("", " 10"),
            ("", "10.0"),
            ("", "\u0661\u0660"),
            ("", "9" * 5000),
        ):
            with self.subTest(digest=digest, size_length=len(size)):
                if not digest:
                    digest = encoded_digest(data)
                raw, payload = record_wheel(
                    "aethron", declared_record("aethron/module.py", digest, size), complete=True
                )
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.validate_source_payload(raw, payload)

    def test_self_record_cannot_declare_hash_or_size(self):
        for digest, size in ((encoded_digest(b""), ""), ("", "0")):
            raw, payload = record_wheel(
                "aethron",
                declared_record("aethron-0.2.0.dist-info/RECORD", digest, size),
                complete=True,
            )
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload)

    def test_optional_size_and_leading_zero_size_remain_accepted(self):
        # Wheel hashes are required; size remains independently checked when supplied.
        for digest, size in (
            (encoded_digest(b"VALUE = 1\n"), "00010"),
            (encoded_digest(b"VALUE = 1\n"), ""),
        ):
            raw, payload = record_wheel(
                "aethron", declared_record("aethron/module.py", digest, size), complete=True
            )
            package_check.validate_source_payload(raw, payload)
        raw, payload = record_wheel(
            "aethron", declared_record("aethron-0.2.0.dist-info/RECORD"), complete=True
        )
        package_check.validate_source_payload(raw, payload)
