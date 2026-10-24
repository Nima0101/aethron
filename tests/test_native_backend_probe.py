"""Negative controls for the synthetic optional-native comparison."""

import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import url2pathname

from scripts import native_backend_probe as probe


class NativeBackendProbe(unittest.TestCase):
    def test_portable_tag_must_not_claim_native_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "fixture.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    "probe_native-0.0.1.dist-info/WHEEL",
                    "Root-Is-Purelib: true\nTag: cp313-cp313-linux_x86_64\n",
                )
            with self.assertRaises(AssertionError):
                probe.validate_wheel(wheel, {}, False)

    def test_native_mode_requires_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "fixture.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    "probe_native-0.0.1.dist-info/WHEEL",
                    "Root-Is-Purelib: false\nTag: cp313-cp313-linux_x86_64\n",
                )
            with self.assertRaises(AssertionError):
                probe.validate_wheel(wheel, {}, True)

    def test_archive_rejects_traversal_links_and_multiple_roots(self):
        for defect in ("traversal", "link", "multiple_roots"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "fixture.tar.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    paths = (
                        ["first/kernel.py", "second/kernel.py"]
                        if defect == "multiple_roots"
                        else ["../escape" if defect == "traversal" else "link"]
                    )
                    for path in paths:
                        member = tarfile.TarInfo(path)
                        if defect == "link":
                            member.type = tarfile.SYMTYPE
                            member.linkname = "../escape"
                        else:
                            member.size = 1
                        tar.addfile(member, io.BytesIO(b"x"))
                target = root / "out"
                target.mkdir()
                with self.assertRaises(AssertionError):
                    probe.extract_sdist(archive, target)
                self.assertFalse((root / "escape").exists())

    def test_artifact_snapshots_bind_extraction_install_and_report(self):
        for mutation in (
            None,
            "sdist_after_read",
            "sdist_after_extract",
            "wheel_after_read",
            "wheel_after_validation",
            "wheel_after_install",
        ):
            with self.subTest(mutation=mutation):
                self.check_artifact_snapshot(mutation)

    def check_artifact_snapshot(self, mutation):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "out"
            artifacts = {}
            expected = {}
            installs = []
            consumers = []
            read_bytes = Path.read_bytes
            validate = probe.validate_wheel
            extract = probe.extract_sdist

            def read(path):
                data = read_bytes(path)
                if mutation == "sdist_after_read" and path == artifacts.get("sdist"):
                    path.write_bytes(b"replaced after captured archive read")
                if mutation == "wheel_after_read" and path == artifacts.get("wheel"):
                    path.write_bytes(b"replaced after captured wheel read")
                return data

            def extract_then_replace(archive, target):
                source = extract(archive, target)
                if mutation == "sdist_after_extract":
                    artifacts["sdist"].write_bytes(b"replaced after extraction")
                return source

            def validate_then_replace(wheel, payload, native):
                validate(wheel, payload, native)
                if mutation == "wheel_after_validation":
                    artifacts["wheel"].write_bytes(b"replaced after validation")

            def run(args, **kwargs):
                result = ""
                rc = 0
                if args[0] == "git":
                    pass
                elif args[1] == "-c":
                    target = Path(args[5])
                    source = Path(kwargs["cwd"])
                    if args[4] == "build_sdist":
                        archive = target / "probe.tar.gz"
                        with tarfile.open(archive, "w:gz") as tar:
                            for file in sorted((source / "probe_pkg").iterdir()):
                                tar.add(
                                    file, arcname="probe/" + file.relative_to(source).as_posix()
                                )
                        artifacts["sdist"] = archive
                        expected["sdist"] = hashlib.sha256(read_bytes(archive)).hexdigest()
                    else:
                        native = kwargs["env"]["PROBE_NATIVE"] == "1"
                        wheel = target / "probe_native-0.0.1-py3-none-any.whl"
                        with zipfile.ZipFile(wheel, "w") as archive:
                            for file in sorted((source / "probe_pkg").iterdir()):
                                archive.writestr(
                                    file.relative_to(source).as_posix(), read_bytes(file)
                                )
                            archive.writestr(
                                "probe_native-0.0.1.dist-info/WHEEL",
                                "Root-Is-Purelib: "
                                + str(not native).lower()
                                + "\nTag: "
                                + ("cp313-cp313-linux_x86_64" if native else "py3-none-any")
                                + "\n",
                            )
                            if native:
                                archive.writestr(
                                    "probe_pkg/kernel"
                                    + probe.importlib.machinery.EXTENSION_SUFFIXES[0],
                                    b"synthetic-only",
                                )
                        artifacts["wheel"] = wheel
                        expected[native] = hashlib.sha256(read_bytes(wheel)).hexdigest()
                elif args[1:4] == ["-m", "pip", "install"]:
                    installs.append(args)
                    uri = urlsplit(args[-1])
                    if uri.scheme == "file":
                        wheel = Path(url2pathname(uri.path))
                        rc = int(
                            uri.fragment
                            != "sha256=" + hashlib.sha256(read_bytes(wheel)).hexdigest()
                        )
                    if mutation == "wheel_after_install" and rc == 0:
                        artifacts["wheel"].write_bytes(b"replaced after installation")
                elif args[1] == "-I":
                    consumers.append(args)
                    result = "synthetic-native-parity-ok\n"
                else:
                    self.fail("unexpected subprocess: " + repr(args))
                return subprocess.CompletedProcess(args, rc, result, "")

            with (
                patch.object(
                    probe.sys,
                    "argv",
                    [
                        "probe",
                        "--tools",
                        str(root),
                        "--out",
                        str(out),
                        "--backend",
                        "setuptools",
                    ],
                ),
                patch.object(probe.subprocess, "run", side_effect=run),
                patch.object(Path, "read_bytes", read),
                patch.object(probe, "validate_wheel", side_effect=validate_then_replace),
                patch.object(probe, "extract_sdist", side_effect=extract_then_replace),
            ):
                if mutation in ("wheel_after_read", "wheel_after_validation"):
                    with self.assertRaises(subprocess.CalledProcessError):
                        probe.main()
                    self.assertFalse(consumers)
                    self.assertFalse((out / "results.json").exists())
                else:
                    probe.main()
                    records = json.loads((out / "results.json").read_text())
                    self.assertEqual(len(records), 2)
                    for record, command in zip(records, installs):
                        self.assertEqual(record["sdist_sha256"], expected["sdist"])
                        self.assertEqual(record["wheel_sha256"], expected[record["native"]])
                        self.assertIn("--require-hashes", command)
                        self.assertIn("--force-reinstall", command)
                        self.assertEqual(
                            urlsplit(command[-1]).fragment,
                            "sha256=" + expected[record["native"]],
                        )
