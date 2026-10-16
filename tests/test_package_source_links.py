"""Reject reparse redirects before source snapshots or installed payload claims."""

import contextlib
import hashlib
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import package_check


@contextlib.contextmanager
def windows_attributes(path, attributes):
    """Model Windows lstat metadata without claiming native junction execution."""
    original = Path.lstat

    def inspect(candidate, *args, **kwargs):
        info = original(candidate, *args, **kwargs)
        if candidate == path:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=attributes)
        return info

    with patch.object(Path, "lstat", inspect):
        yield


class PackageSourceLinks(unittest.TestCase):
    def test_reparse_sources_reject_before_redirected_payload_reads(self):
        for package in ("aethron", "aethron_edge"):
            for location in (package, f"{package}/models", f"{package}/models/rules.json"):
                with self.subTest(package=package, location=location):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        source = root / package / "models/rules.json"
                        source.parent.mkdir(parents=True)
                        source.write_bytes(b"{}")
                        with (
                            windows_attributes(root / location, stat.FILE_ATTRIBUTE_REPARSE_POINT),
                            patch.object(Path, "read_bytes") as read,
                        ):
                            with self.assertRaisesRegex(ValueError, "invalid_source_payload_file"):
                                package_check.snapshot_source_payload(root, package)
                            read.assert_not_called()

    def test_installed_manifest_rejects_reparse_sources_inside_environment(self):
        for package, distribution in (("aethron", "aethron"), ("aethron_edge", "aethron-edge")):
            for nested in (False, True):
                with self.subTest(package=package, nested=nested):
                    with tempfile.TemporaryDirectory() as directory:
                        prefix = Path(directory)
                        root = prefix / "site-packages"
                        source = root / package / "models/rules.json"
                        source.parent.mkdir(parents=True)
                        source.write_bytes(b"{}")
                        redirect = source.parent if nested else root / package
                        with (
                            windows_attributes(redirect, stat.FILE_ATTRIBUTE_REPARSE_POINT),
                            patch.object(package_check.sys, "prefix", str(prefix)),
                            patch.object(package_check.importlib.metadata, "distribution") as dist,
                        ):
                            dist.return_value.locate_file.return_value = root / package
                            with self.assertRaisesRegex(ValueError, "invalid_source_payload_file"):
                                package_check.installed_source_manifest(package, distribution)

    def test_ordinary_windows_attributes_preserve_source_and_installed_hashes(self):
        for package, distribution in (("aethron", "aethron"), ("aethron_edge", "aethron-edge")):
            with self.subTest(package=package), tempfile.TemporaryDirectory() as directory:
                prefix = Path(directory)
                source = prefix / package / "rules.json"
                source.parent.mkdir()
                source.write_bytes(b"{}")
                with (
                    windows_attributes(
                        source, stat.FILE_ATTRIBUTE_ARCHIVE | stat.FILE_ATTRIBUTE_READONLY
                    ),
                    patch.object(package_check.sys, "prefix", str(prefix)),
                    patch.object(package_check.importlib.metadata, "distribution") as dist,
                ):
                    dist.return_value.locate_file.return_value = source.parent
                    self.assertEqual(
                        package_check.snapshot_source_payload(prefix, package),
                        {f"{package}/rules.json": b"{}"},
                    )
                    self.assertEqual(
                        package_check.installed_source_manifest(package, distribution),
                        {f"{package}/rules.json": hashlib.sha256(b"{}").hexdigest()},
                    )
