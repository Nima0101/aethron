"""Equal wheels must also match the selected source payload captured before build."""

import contextlib
import io
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_check


class CorePackagePayload(unittest.TestCase):
    def check_payload(self, defect=None, mutate_source=False):
        payload = {
            "aethron/__init__.py": b"# current source\n",
            "aethron/models/rules.json": b'{"synthetic":true}\n',
            "aethron/_bounds.pxd": b"# current declaration\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in payload.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            wheel = io.BytesIO()
            records = list(payload.items())
            if defect == "changed":
                records[0] = (records[0][0], b"# stale source\n")
            elif defect == "missing":
                records.pop()
            elif defect == "extra":
                records.append(("aethron/retired.py", b"# stale extra file\n"))
            elif defect == "duplicate":
                records.append(records[0])
            elif defect == "path-alias":
                records.append(("./" + records[0][0], b"# replaced source\n"))
            elif defect == "case-alias":
                records.append((records[0][0].upper(), b"# replaced source\n"))
            elif defect and defect.startswith("spread-"):
                _, scheme, kind = defect.split("-")
                name = "aethron/retired.py" if kind == "extra" else records[0][0]
                records.append((f"aethron-0.2.0.data/{scheme}/{name}", b"# stale source\n"))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(wheel, "w") as archive:
                    for name, data in records:
                        archive.writestr(name, data)
                    archive.writestr(
                        "aethron/_bounds.synthetic.so", b"not covered by source parity"
                    )
            calls = []

            def process(args, **kwargs):
                calls.append(args)
                if args[1:4] == ["-m", "build", "--no-isolation"]:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir()
                    (destination / "aethron-0.2.0-py3-none-any.whl").write_bytes(wheel.getvalue())
                    if mutate_source:
                        (root / "aethron/__init__.py").write_bytes(b"# replaced during build\n")
                    return subprocess.CompletedProcess(args, 0)
                raise RuntimeError("consumer_boundary")

            output = io.StringIO()
            with (
                patch.object(tempfile, "tempdir", directory),
                patch.object(package_check, "ROOT", root),
                patch.object(package_check.subprocess, "run", side_effect=process),
                contextlib.redirect_stdout(output),
            ):
                if defect:
                    with self.assertRaises(Exception) as raised:
                        package_check.run()
                    self.assertIsInstance(raised.exception, ValueError)
                    self.assertEqual(str(raised.exception), "wheel_source_payload_mismatch")
                    self.assertEqual(len(calls), 2, "reject before environment/install/consumer")
                else:
                    with self.assertRaisesRegex(RuntimeError, "consumer_boundary"):
                        package_check.run()
                    self.assertEqual(len(calls), 3)
            self.assertEqual(output.getvalue(), "")

    def test_identical_stale_or_incomplete_wheels_are_rejected(self):
        for defect in ("changed", "missing", "extra", "duplicate"):
            with self.subTest(defect=defect):
                self.check_payload(defect)

    def test_matching_payload_reaches_consumer(self):
        self.check_payload()

    def test_path_alias_is_rejected_before_installation(self):
        self.check_payload("path-alias")

    def test_case_alias_is_rejected_before_installation(self):
        self.check_payload("case-alias")

    def test_case_aliases_cannot_override_or_extend_package_sources(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for alias in (
                    f"{package.upper()}/module.py",
                    f"{package}/module.PY",
                    f"{package.upper()}/extra.py",
                    f"{package}/extra.JSON",
                    f"{package}/extra.PXD",
                ):
                    with self.subTest(package=package, prefix=prefix, alias=alias):
                        archive = io.BytesIO()
                        with zipfile.ZipFile(archive, "w") as wheel:
                            wheel.writestr(name, payload[name])
                            wheel.writestr(prefix + alias, b"VALUE = 2\n")
                        with self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"):
                            package_check.validate_source_payload(
                                archive.getvalue(), payload, package
                            )

    def test_case_colliding_source_snapshot_is_not_portable(self):
        payload = {"aethron/module.py": b"one\n", "aethron/Module.py": b"two\n"}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            for name, data in payload.items():
                wheel.writestr(name, data)
        with self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"):
            package_check.validate_source_payload(archive.getvalue(), payload)

    def test_unique_mixed_case_source_names_are_allowed(self):
        payload = {"aethron/MixedCase.py": b"VALUE = 1\n", "aethron/models/Caf\u00e9.json": b"{}"}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            for name, data in payload.items():
                wheel.writestr(name, data)
        package_check.validate_source_payload(archive.getvalue(), payload)

    def test_noncanonical_member_paths_are_rejected_for_core_and_edge(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            aliases = (
                "./" + name,
                "unused/../" + name,
                "/" + name,
                "C:/" + name,
                name.replace("/", "\\"),
                f"{package}-0.2.0.data//purelib/{name}",
                f"{package}-0.2.0.data/./platlib/{name}",
                f"{package}-0.2.0.data/purelib/unused/../{name}",
                f"{package}-0.2.0.data/platlib//{name}",
            )
            for alias in aliases:
                with self.subTest(package=package, alias=alias):
                    archive = io.BytesIO()
                    with zipfile.ZipFile(archive, "w") as wheel:
                        wheel.writestr(name, payload[name])
                        wheel.writestr(alias, b"VALUE = 2\n")
                    with self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"):
                        package_check.validate_source_payload(archive.getvalue(), payload, package)

    def test_canonical_directory_records_and_unicode_resources_are_allowed(self):
        payload = {"aethron/module.py": b"VALUE = 1\n"}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            wheel.writestr("aethron/", b"")
            wheel.writestr("aethron/module.py", payload["aethron/module.py"])
            wheel.writestr("aethron-0.2.0.dist-info/licenses/", b"")
            wheel.writestr("aethron-0.2.0.dist-info/licenses/caf\u00e9.txt", b"license\n")
        package_check.validate_source_payload(archive.getvalue(), payload)

    def test_spread_payload_cannot_override_or_extend_verified_sources(self):
        for scheme in ("purelib", "platlib"):
            for kind in ("override", "extra"):
                with self.subTest(scheme=scheme, kind=kind):
                    self.check_payload(f"spread-{scheme}-{kind}")

    def test_spread_payload_uses_installed_names_for_core_and_edge(self):
        for package in ("aethron", "aethron_edge"):
            for scheme in ("purelib", "platlib"):
                for changed in (False, True):
                    with self.subTest(package=package, scheme=scheme, changed=changed):
                        payload = {f"{package}/module.py": b"VALUE = 1\n"}
                        archive = io.BytesIO()
                        with zipfile.ZipFile(archive, "w") as wheel:
                            wheel.writestr(
                                f"{package}-0.2.0.data/{scheme}/{package}/module.py",
                                b"VALUE = 2\n" if changed else payload[f"{package}/module.py"],
                            )
                            # Data installed outside the import scheme is not package source.
                            wheel.writestr(
                                f"{package}-0.2.0.data/data/{package}/example.py", b"# example\n"
                            )
                        if changed:
                            with self.assertRaisesRegex(
                                ValueError, "wheel_source_payload_mismatch"
                            ):
                                package_check.validate_source_payload(
                                    archive.getvalue(), payload, package
                                )
                        else:
                            package_check.validate_source_payload(
                                archive.getvalue(), payload, package
                            )

    def test_duplicate_install_destinations_reject_even_when_bytes_agree(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            paths = (
                name,
                f"{package}-0.2.0.data/purelib/{name}",
                f"{package}-0.2.0.data/platlib/{name}",
            )
            for first in paths:
                for second in paths:
                    if first == second:
                        continue
                    with self.subTest(package=package, first=first, second=second):
                        archive = io.BytesIO()
                        with zipfile.ZipFile(archive, "w") as wheel:
                            for member in (first, second):
                                wheel.writestr(member, payload[name])
                        with self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"):
                            package_check.validate_source_payload(
                                archive.getvalue(), payload, package
                            )

    def test_comparison_uses_prebuild_snapshot(self):
        self.check_payload(mutate_source=True)

    def test_empty_or_nonfile_source_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "empty_source_payload"):
                package_check.snapshot_source_payload(root)
            (root / "aethron/fake.py").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "invalid_source_payload_file"):
                package_check.snapshot_source_payload(root)

    def test_symlinked_source_directories_are_rejected(self):
        for location in ("aethron", "aethron/models"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "source"
                target = Path(directory) / "external"
                target.mkdir()
                (target / "rules.json").write_bytes(b"{}")
                link = root / location
                link.parent.mkdir(parents=True)
                link.symlink_to(target, target_is_directory=True)
                if location != "aethron":
                    (root / "aethron/__init__.py").write_bytes(b"")
                with self.assertRaisesRegex(ValueError, "invalid_source_payload_file"):
                    package_check.snapshot_source_payload(root)
