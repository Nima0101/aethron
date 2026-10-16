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
            (root / "pyproject.toml").write_text(
                '[project]\nversion = "0.2.0"\nrequires-python = ">=3.9"\n'
                'license = "GPL-3.0-only"\n'
            )
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
            elif defect == "trailing-dot":
                records.append((records[0][0] + ".", b"# replaced source\n"))
            elif defect == "trailing-space":
                records.append((records[0][0] + " ", b"# replaced source\n"))
            elif defect == "nul-name":
                records.append(("aethron/notes.txt@ignored", b"resource\n"))
            elif defect == "device-name":
                records.append(("aethron/NUL.txt", b"not an ordinary file on Windows\n"))
            elif defect == "reserved-character":
                records.append(("aethron/notes?.txt", b"not a portable filename\n"))
            elif defect == "resource-collision":
                records.extend(
                    (("aethron/notes.txt", b"first\n"), ("aethron/NOTES.txt", b"second\n"))
                )
            elif defect == "directory-conflict":
                records.extend((("aethron/assets", b"file"), ("aethron/assets/a.txt", b"")))
            elif defect == "startup-path":
                records.append(("unexpected.pth", b"import sys\n"))
            elif defect == "bytecode":
                records.append(("aethron/retired.pyc", b"unchecked bytecode\n"))
            elif defect == "startup-module":
                records.append(("sitecustomize.py", b"import sys\n"))
            elif defect == "startup-package":
                records.append(("sitecustomize/__init__.py", b"import sys\n"))
            elif defect == "data-import-directory":
                records.append(
                    ("aethron-0.2.0.data/data/Lib/site-packages/fixture.pth", b"# inert\n")
                )
            elif defect == "script-destination":
                records.append(("aethron-0.2.0.data/scripts/fixture-tool", b"# inert\n"))
            elif defect == "entry-points":
                records.append(
                    (
                        "aethron-0.2.0.dist-info/entry_points.txt",
                        b"[console_scripts]\nfixture-tool = fixture:main\n",
                    )
                )
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
                    archive.writestr(
                        "aethron-0.2.0.dist-info/METADATA",
                        "Metadata-Version: 2.1\nName: aethron\nVersion: 0.2.0\nRequires-Python: >=3.9\n"
                        "License-Expression: GPL-3.0-only\n",
                    )
            wheel_bytes = wheel.getvalue()
            if defect == "nul-name":
                wheel_bytes = wheel_bytes.replace(b"notes.txt@ignored", b"notes.txt\x00ignored")
            calls = []

            def process(args, **kwargs):
                calls.append(args)
                if args[1:4] == ["-m", "build", "--no-isolation"]:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir()
                    # This fixture deliberately includes an owned native file;
                    # portable wheels reject it independently of source parity.
                    (destination / "aethron-0.2.0-py3-none-linux_x86_64.whl").write_bytes(
                        wheel_bytes
                    )
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

    def test_resource_collision_is_rejected_before_installation(self):
        self.check_payload("resource-collision")

    def test_data_import_directory_is_rejected_before_installation(self):
        self.check_payload("data-import-directory")

    def test_script_destination_is_rejected_before_installation(self):
        self.check_payload("script-destination")

    def test_undeclared_entry_points_reject_before_installation(self):
        self.check_payload("entry-points")

    def test_all_file_destinations_reject_collisions_before_source_reads(self):
        for package in ("aethron", "aethron_edge"):
            payload = {f"{package}/__init__.py": b""}
            for name in (f"{package}/notes.txt", f"{package}-0.2.0.dist-info/METADATA"):
                paths = (
                    name,
                    name.upper(),
                    f"{package}-0.2.0.data/purelib/{name}",
                    f"{package}-0.2.0.data/platlib/{name}",
                )
                for first in paths:
                    for second in paths:
                        for content in (b"first", b"different"):
                            with self.subTest(
                                package=package, first=first, second=second, content=content
                            ):
                                archive = io.BytesIO()
                                with warnings.catch_warnings():
                                    warnings.simplefilter("ignore", UserWarning)
                                    with zipfile.ZipFile(archive, "w") as wheel:
                                        wheel.writestr(f"{package}/__init__.py", b"")
                                        wheel.writestr(first, b"first")
                                        wheel.writestr(second, content)
                                with (
                                    patch.object(
                                        zipfile.ZipFile,
                                        "read",
                                        side_effect=AssertionError("premature read"),
                                    ),
                                    self.assertRaisesRegex(
                                        ValueError, "wheel_source_payload_mismatch"
                                    ),
                                ):
                                    package_check.validate_source_payload(
                                        archive.getvalue(), payload, package
                                    )

    def test_directory_conflict_is_rejected_before_installation(self):
        self.check_payload("directory-conflict")

    def test_file_directory_conflicts_reject_before_reads(self):
        for package in ("aethron", "aethron_edge"):
            payload = {f"{package}/__init__.py": b""}
            prefixes = ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/")
            for file_name, directory_name in (
                (f"{package}/assets", f"{package}/assets/"),
                (f"{package}/assets", f"{package}/assets/deep/readme.txt"),
                (f"{package}/assets", f"{package}/ASSETS/deep/"),
                (f"{package}-0.2.0.dist-info", f"{package}-0.2.0.dist-info/METADATA"),
            ):
                for file_prefix in prefixes:
                    for directory_prefix in prefixes:
                        for reverse in (False, True):
                            entries = [file_prefix + file_name, directory_prefix + directory_name]
                            if reverse:
                                entries.reverse()
                            with self.subTest(package=package, entries=entries):
                                archive = io.BytesIO()
                                with zipfile.ZipFile(archive, "w") as wheel:
                                    wheel.writestr(f"{package}/__init__.py", b"")
                                    for name in entries:
                                        wheel.writestr(name, b"")
                                with (
                                    patch.object(
                                        zipfile.ZipFile,
                                        "read",
                                        side_effect=AssertionError("premature read"),
                                    ),
                                    self.assertRaisesRegex(
                                        ValueError, "wheel_source_payload_mismatch"
                                    ),
                                ):
                                    package_check.validate_source_payload(
                                        archive.getvalue(), payload, package
                                    )

    def test_shared_directories_and_nonancestor_files_remain_allowed(self):
        for package in ("aethron", "aethron_edge"):
            payload = {f"{package}/__init__.py": b""}
            entries = [
                f"{package}/assets/one.txt",
                f"{package}/assets/two.txt",
                f"{package}/assets/",
                f"{package}/ASSETS/",
                f"{package}/asset",
                f"{package}/asset-other/three.txt",
                f"{package}-0.2.0.data/purelib/{package}/assets/",
                f"{package}-0.2.0.data/platlib/{package}/assets/four.txt",
            ]
            for order in (entries, list(reversed(entries))):
                with self.subTest(package=package, order=order):
                    archive = io.BytesIO()
                    with zipfile.ZipFile(archive, "w") as wheel:
                        wheel.writestr(f"{package}/__init__.py", b"")
                        for name in order:
                            wheel.writestr(name, b"")
                    package_check.validate_source_payload(archive.getvalue(), payload, package)

    def test_distinct_resources_and_explicit_directories_remain_allowed(self):
        for package in ("aethron", "aethron_edge"):
            payload = {f"{package}/__init__.py": b""}
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as wheel:
                for name, content in payload.items():
                    wheel.writestr(name, content)
                for name in (
                    f"{package}/",
                    f"{package}/assets/",
                    f"{package}/assets/a.txt",
                    f"{package}/other/a.txt",
                    f"{package}-0.2.0.data/purelib/{package}/assets/b.txt",
                    f"{package}-0.2.0.data/platlib/{package}/assets/c.txt",
                    f"{package}-0.2.0.data/data/{package}/assets/a.txt",
                ):
                    wheel.writestr(name, b"")
                wheel.writestr(
                    f"{package}-0.2.0.dist-info/METADATA",
                    f"Metadata-Version: 2.1\nName: {package}\nVersion: 0.2.0\n",
                )
            package_check.validate_source_payload(archive.getvalue(), payload, package)

    def test_device_name_is_rejected_before_installation(self):
        self.check_payload("device-name")

    def test_reserved_character_is_rejected_before_installation(self):
        self.check_payload("reserved-character")

    def test_reserved_characters_reject_before_reads_for_core_and_edge(self):
        # Independent Windows filename rules: slash is the ZIP separator;
        # backslash/colon and NUL already have separate regression coverage.
        characters = '<>"|?*' + "".join(chr(value) for value in range(1, 32))
        for package in ("aethron", "aethron_edge"):
            payload = {f"{package}/__init__.py": b""}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for character in characters:
                    for ending in (".txt", "/data.txt", "/"):
                        with self.subTest(
                            package=package, prefix=prefix, char=character, end=ending
                        ):
                            archive = io.BytesIO()
                            with zipfile.ZipFile(archive, "w") as wheel:
                                wheel.writestr(f"{package}/__init__.py", b"")
                                wheel.writestr(
                                    prefix + package + "/notes" + character + ending, b""
                                )
                            with (
                                patch.object(
                                    zipfile.ZipFile,
                                    "read",
                                    side_effect=AssertionError("source read before path rejection"),
                                ),
                                self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"),
                            ):
                                package_check.validate_source_payload(
                                    archive.getvalue(), payload, package
                                )

    def test_reserved_characters_reject_matching_source_and_metadata(self):
        for name in ("aethron/module?.py", "aethron-0.2.0.dist-info/notes\n.txt", "extra*.txt"):
            with self.subTest(name=name):
                payload = {"aethron/__init__.py": b""}
                if name.endswith(".py"):
                    payload[name] = b""
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w") as wheel:
                    wheel.writestr("aethron/__init__.py", b"")
                    wheel.writestr(name, b"")
                with self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"):
                    package_check.validate_source_payload(archive.getvalue(), payload)

    def test_valid_punctuation_and_unicode_filenames_remain_allowed(self):
        names = (
            "notes !#$%&'()+,-;=@[]^_`{}~",
            "r\u00e9sum\u00e9",
            "\u8cc7\u6599",
            "a\u00a0b",
            "a\x7fb",
        )
        for package in ("aethron", "aethron_edge"):
            payload = {f"{package}/{name}.py": b"# ordinary source\n" for name in names}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                with self.subTest(package=package, prefix=prefix):
                    archive = io.BytesIO()
                    with zipfile.ZipFile(archive, "w") as wheel:
                        for name, data in payload.items():
                            wheel.writestr(prefix + name, data)
                    package_check.validate_source_payload(archive.getvalue(), payload, package)

    def test_reserved_devices_reject_before_reads_for_core_and_edge(self):
        devices = ("CON", "PRN", "AUX", "NUL") + tuple(
            prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"
        )
        for package in ("aethron", "aethron_edge"):
            payload = {f"{package}/__init__.py": b""}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for device in devices:
                    for path in (device, device.lower() + ".txt", device + "/data.txt"):
                        with self.subTest(package=package, prefix=prefix, path=path):
                            archive = io.BytesIO()
                            with zipfile.ZipFile(archive, "w") as wheel:
                                for name, data in payload.items():
                                    wheel.writestr(name, data)
                                wheel.writestr(prefix + package + "/" + path, b"resource")
                            with (
                                patch.object(
                                    zipfile.ZipFile,
                                    "read",
                                    side_effect=AssertionError(
                                        "source read before device rejection"
                                    ),
                                ),
                                self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"),
                            ):
                                package_check.validate_source_payload(
                                    archive.getvalue(), payload, package
                                )

    def test_device_named_directories_and_metadata_are_rejected(self):
        for name in ("CON/", "aux.txt/", "aethron-0.2.0.dist-info/NUL.txt", "COM1.data/file"):
            with self.subTest(name=name):
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w") as wheel:
                    wheel.writestr("aethron/__init__.py", b"")
                    wheel.writestr(name, b"")
                with self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"):
                    package_check.validate_source_payload(
                        archive.getvalue(), {"aethron/__init__.py": b""}
                    )

    def test_names_adjacent_to_devices_remain_allowed(self):
        names = (
            "console",
            "auxiliary",
            "null",
            "COM0",
            "COM10",
            "LPT0",
            "LPT10",
            "COM⁴",
            "_NUL",
            "x.CON",
        )
        for package in ("aethron", "aethron_edge"):
            payload = {f"{package}/{name}.py": b"# ordinary source\n" for name in names}
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as wheel:
                for name, data in payload.items():
                    wheel.writestr(name, data)
            package_check.validate_source_payload(archive.getvalue(), payload, package)

    def test_startup_path_is_rejected_before_installation(self):
        self.check_payload("startup-path")

    def test_bytecode_is_rejected_before_installation(self):
        self.check_payload("bytecode")

    def test_startup_modules_are_rejected_before_installation(self):
        for defect in ("startup-module", "startup-package"):
            with self.subTest(defect=defect):
                self.check_payload(defect)

    def test_startup_modules_reject_before_source_reads_for_core_and_edge(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for module in ("sitecustomize", "usercustomize", "SiteCustomize", "USERCUSTOMIZE"):
                    for suffix in (".py", "/__init__.py", ".abi3.so", ".cp313-win_amd64.pyd"):
                        with self.subTest(
                            package=package, prefix=prefix, module=module, suffix=suffix
                        ):
                            archive = io.BytesIO()
                            with zipfile.ZipFile(archive, "w") as wheel:
                                wheel.writestr(name, payload[name])
                                wheel.writestr(
                                    prefix + module + suffix, b"unchecked startup module"
                                )
                            with (
                                patch.object(
                                    zipfile.ZipFile,
                                    "read",
                                    side_effect=AssertionError(
                                        "source read before startup rejection"
                                    ),
                                ),
                                self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"),
                            ):
                                package_check.validate_source_payload(
                                    archive.getvalue(), payload, package
                                )

    def test_nested_customization_sources_and_unrelated_resources_remain_allowed(self):
        for package in ("aethron", "aethron_edge"):
            payload = {
                f"{package}/__init__.py": b"",
                f"{package}/sitecustomize.py": b"# ordinary nested module\n",
                f"{package}/usercustomize/__init__.py": b"# ordinary nested package\n",
                f"{package}/usercustomize_example.py": b"# ordinary nested module\n",
            }
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                with self.subTest(package=package, prefix=prefix):
                    archive = io.BytesIO()
                    with zipfile.ZipFile(archive, "w") as wheel:
                        for name, data in payload.items():
                            wheel.writestr(prefix + name, data)
                        wheel.writestr(prefix + "sitecustomize.txt", b"documentation")
                        wheel.writestr(f"{package}-0.2.0.dist-info/sitecustomize.py", b"resource")
                    package_check.validate_source_payload(archive.getvalue(), payload, package)

    def test_bytecode_rejects_before_source_reads_for_core_and_edge(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for member in (
                    f"{package}/retired.pyc",
                    f"{package}/__pycache__/module.cpython-313.pyc",
                    f"{package}/__pycache__/module.cpython-313.opt-1.PYC",
                    "unexpected.pyc",
                ):
                    with self.subTest(package=package, prefix=prefix, member=member):
                        archive = io.BytesIO()
                        with zipfile.ZipFile(archive, "w") as wheel:
                            wheel.writestr(name, payload[name])
                            wheel.writestr(prefix + member, b"unchecked bytecode")
                        with (
                            patch.object(
                                zipfile.ZipFile,
                                "read",
                                side_effect=AssertionError("source read before bytecode rejection"),
                            ),
                            self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"),
                        ):
                            package_check.validate_source_payload(
                                archive.getvalue(), payload, package
                            )

    def test_bytecode_named_directories_and_nonbytecode_resources_remain_allowed(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as wheel:
                wheel.writestr(name, payload[name])
                wheel.writestr(f"{package}/resources.pyc/", b"")
                wheel.writestr(f"{package}/resources.pyc/notes.txt", b"resource")
                wheel.writestr(f"{package}/example.pyc.txt", b"resource")
            package_check.validate_source_payload(archive.getvalue(), payload, package)

    def test_site_path_files_reject_before_source_reads_for_core_and_edge(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for suffix in (".pth", ".PTH"):
                    for content in (b"import sys\n", b"extra-import-directory\n", b"# empty\n"):
                        with self.subTest(
                            package=package, prefix=prefix, suffix=suffix, content=content
                        ):
                            archive = io.BytesIO()
                            with zipfile.ZipFile(archive, "w") as wheel:
                                wheel.writestr(name, payload[name])
                                wheel.writestr(prefix + "unexpected" + suffix, content)
                            with (
                                patch.object(
                                    zipfile.ZipFile,
                                    "read",
                                    side_effect=AssertionError(
                                        "source read before startup path rejection"
                                    ),
                                ),
                                self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"),
                            ):
                                package_check.validate_source_payload(
                                    archive.getvalue(), payload, package
                                )

    def test_nested_path_resources_remain_allowed(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                with self.subTest(package=package, prefix=prefix):
                    archive = io.BytesIO()
                    with zipfile.ZipFile(archive, "w") as wheel:
                        wheel.writestr(name, payload[name])
                        wheel.writestr(prefix + f"{package}/resources/model.pth", b"resource")
                        wheel.writestr(prefix + "directory.pth/", b"")
                    package_check.validate_source_payload(archive.getvalue(), payload, package)

    def test_path_alias_is_rejected_before_installation(self):
        self.check_payload("path-alias")

    def test_case_alias_is_rejected_before_installation(self):
        self.check_payload("case-alias")

    def test_nul_member_is_rejected_before_installation(self):
        self.check_payload("nul-name")

    def test_nul_member_names_reject_before_source_reads_for_core_and_edge(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for member in (name, f"{package}/notes.txt", f"{package}/resources/"):
                    with self.subTest(package=package, prefix=prefix, member=member):
                        archive = io.BytesIO()
                        encoded = (prefix + member + "@ignored").encode()
                        with zipfile.ZipFile(archive, "w") as wheel:
                            if member != name:
                                wheel.writestr(name, payload[name])
                            wheel.writestr(encoded.decode(), payload[name])
                        # Patch both ZIP headers after writing: ZipInfo itself
                        # truncates NUL names, so writestr cannot create this case.
                        raw = archive.getvalue()
                        self.assertEqual(raw.count(encoded), 2)
                        raw = raw.replace(encoded, encoded.replace(b"@", b"\x00"))
                        with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
                            self.assertIn("\x00", wheel.infolist()[-1].orig_filename)
                            self.assertNotIn("\x00", wheel.infolist()[-1].filename)
                        with (
                            patch.object(
                                zipfile.ZipFile,
                                "read",
                                side_effect=AssertionError(
                                    "payload read before malformed name rejection"
                                ),
                            ),
                            self.assertRaisesRegex(ValueError, "wheel_source_payload_mismatch"),
                        ):
                            package_check.validate_source_payload(raw, payload, package)

    def test_trailing_dot_or_space_is_rejected_before_installation(self):
        for defect in ("trailing-dot", "trailing-space"):
            with self.subTest(defect=defect):
                self.check_payload(defect)

    def test_nonportable_component_endings_are_rejected_for_core_and_edge(self):
        for package in ("aethron", "aethron_edge"):
            name = f"{package}/module.py"
            payload = {name: b"VALUE = 1\n"}
            for prefix in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for ending in (".", " ", "..", ". "):
                    for alias in (
                        name + ending,
                        f"{package}{ending}/module.py",
                        f"{package}/resources{ending}/notes.txt",
                        f"{package}/resources{ending}/",
                    ):
                        with self.subTest(package=package, prefix=prefix, alias=alias):
                            archive = io.BytesIO()
                            with zipfile.ZipFile(archive, "w") as wheel:
                                wheel.writestr(name, payload[name])
                                wheel.writestr(prefix + alias, b"replacement\n")
                            with self.assertRaisesRegex(
                                ValueError, "wheel_source_payload_mismatch"
                            ):
                                package_check.validate_source_payload(
                                    archive.getvalue(), payload, package
                                )

    def test_internal_dots_spaces_and_leading_dots_are_allowed(self):
        payload = {"aethron/module.py": b"VALUE = 1\n"}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            wheel.writestr("aethron/module.py", payload["aethron/module.py"])
            wheel.writestr("aethron/.resources/", b"")
            wheel.writestr("aethron/.resources/caf\u00e9 notes.v1.txt", b"resource\n")
        package_check.validate_source_payload(archive.getvalue(), payload)

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

    def test_source_snapshot_and_wheel_agree_on_mixed_case_suffixes(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                payload = {
                    f"{package}/__init__.py": b"# source\n",
                    f"{package}/module.PY": b"VALUE = 1\n",
                    f"{package}/models/Caf\u00e9.JsOn": b"{}\n",
                    f"{package}/bounds.PxD": b"# declaration\n",
                }
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w") as wheel:
                    for name, data in payload.items():
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                        wheel.writestr(name, data)
                (root / package / "notes.TXT").write_bytes(b"outside source parity\n")
                snapshot = package_check.snapshot_source_payload(root, package)
                self.assertEqual(snapshot, payload)
                package_check.validate_source_payload(archive.getvalue(), snapshot, package)

    def test_mixed_case_source_directories_and_symlinks_are_rejected(self):
        for package in ("aethron", "aethron_edge"):
            for suffix in (".PY", ".JsOn", ".PxD"):
                for kind in ("directory", "symlink", "dangling-symlink"):
                    with (
                        self.subTest(package=package, suffix=suffix, kind=kind),
                        tempfile.TemporaryDirectory() as directory,
                    ):
                        root = Path(directory)
                        (root / package).mkdir()
                        (root / package / "__init__.py").write_bytes(b"# source\n")
                        path = root / package / ("invalid" + suffix)
                        if kind == "directory":
                            path.mkdir()
                        else:
                            target = root / "external"
                            if kind == "symlink":
                                target.write_bytes(b"# outside package\n")
                            path.symlink_to(target)
                        with self.assertRaisesRegex(ValueError, "invalid_source_payload_file"):
                            package_check.snapshot_source_payload(root, package)

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
