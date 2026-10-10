"""Negative controls for synthetic build evidence, without loading backends."""

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import url2pathname

from scripts import backend_parity_probe as probe


class BackendParityProbe(unittest.TestCase):
    def contents(self):
        return {
            **probe.PAYLOAD,
            "probe_package-0.0.1.dist-info/METADATA": (
                b"Metadata-Version: 2.4\nName: probe-package\nVersion: 0.0.1\n"
                b"Requires-Python: >=3.9\nLicense-Expression: GPL-3.0-only\n\n"
            ),
            "probe_package-0.0.1.dist-info/licenses/LICENSE": b"synthetic license\n",
            "probe_package-0.0.1.dist-info/entry_points.txt": (
                b"[console_scripts]\nprobe-package = probe_pkg:main\n"
            ),
        }

    def validate(self, contents):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "fixture.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for name, value in contents.items():
                    archive.writestr(name, value)
            return probe.validate_wheel(wheel, b"synthetic license\n")

    def test_directory_entries_do_not_change_payload(self):
        self.validate(self.contents())
        self.validate({**self.contents(), "probe_pkg/": b""})

    def test_missing_extra_and_changed_payload_fail(self):
        for defect in ("missing", "extra", "extra_metadata", "changed"):
            with self.subTest(defect=defect):
                contents = self.contents()
                if defect == "missing":
                    del contents["probe_pkg/schema.json"]
                elif defect == "extra":
                    contents["unrelated-private-note.txt"] = b"excluded fixture"
                elif defect == "extra_metadata":
                    contents["unrelated.dist-info/private.txt"] = b"excluded fixture"
                else:
                    contents["probe_pkg/schema.json"] = b"{}"
                with self.assertRaises(AssertionError):
                    self.validate(contents)

    def test_metadata_license_and_entrypoint_changes_fail(self):
        for suffix, replacement in (
            ("/METADATA", b"Name: different\n"),
            ("/licenses/LICENSE", b"different license"),
            ("/entry_points.txt", b"[console_scripts]\nprobe-package=probe_pkg:wrong\n"),
        ):
            with self.subTest(suffix=suffix):
                contents = self.contents()
                name = next(name for name in contents if name.endswith(suffix))
                contents[name] = replacement
                with self.assertRaises(AssertionError):
                    self.validate(contents)

    def test_optimized_interpreter_rejects_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            result = subprocess.run(
                [sys.executable, "-O", probe.__file__, "--tools", directory, "--out", str(output)],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("probe_requires_assertions", result.stderr)
            self.assertFalse(output.exists())

    def test_contract_install_and_report_share_snapshot(self):
        license_bytes = (Path(probe.__file__).resolve().parents[1] / "LICENSE").read_bytes()
        contents = self.contents()
        contents["probe_package-0.0.1.dist-info/licenses/LICENSE"] = license_bytes
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, body in contents.items():
                archive.writestr(name, body)
        original_bytes = buffer.getvalue()
        digest = hashlib.sha256(original_bytes).hexdigest()
        read_bytes = Path.read_bytes
        validate = probe.validate_wheel
        for mutation in (None, "after_read", "after_validation"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / "out # space"
                wheel = out / "setuptools-fixture/b/probe_package-0.0.1-py3-none-any.whl"
                installs = []
                consoles = []

                def read_snapshot(path, mutation=mutation, wheel=wheel):
                    data = read_bytes(path)
                    if path == wheel and mutation == "after_read":
                        path.write_bytes(b"changed after digest read")
                    return data

                def validate_snapshot(value, license_bytes, mutation=mutation, wheel=wheel):
                    members = validate(value, license_bytes)
                    if mutation == "after_validation" and wheel.exists():
                        wheel.write_bytes(b"changed after contract validation")
                    return members

                def process(args, installs=installs, consoles=consoles, **kwargs):
                    if args[1:3] == ["-I", "-c"]:
                        (Path(args[-1]) / "probe_package-0.0.1-py3-none-any.whl").write_bytes(
                            original_bytes
                        )
                    elif args[1:3] == ["-m", "venv"]:
                        pass
                    elif args[1:3] == ["-m", "pip"]:
                        installs.append(args)
                        # Model pip's hash admission; a real-pip negative control is retained
                        # separately. No backend, installer or product is executed here.
                        url = urlsplit(args[-1])
                        if url.fragment.startswith("sha256="):
                            actual = hashlib.sha256(
                                read_bytes(Path(url2pathname(url.path)))
                            ).hexdigest()
                            if actual != url.fragment.removeprefix("sha256="):
                                return subprocess.CompletedProcess(args, 1, "", "hash mismatch")
                    else:
                        consoles.append(args)
                        return subprocess.CompletedProcess(args, 0, "synthetic-ok\n", "")
                    return subprocess.CompletedProcess(args, 0, "", "")

                with (
                    patch.object(
                        sys,
                        "argv",
                        [
                            probe.__file__,
                            "--tools",
                            directory,
                            "--out",
                            str(out),
                            "--backend",
                            "setuptools",
                        ],
                    ),
                    patch.object(Path, "read_bytes", read_snapshot),
                    patch.object(probe, "validate_wheel", validate_snapshot),
                    patch.object(probe.subprocess, "run", side_effect=process),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    if mutation:
                        with self.assertRaises(subprocess.CalledProcessError):
                            probe.main()
                        self.assertFalse((out / "results.json").exists())
                        self.assertEqual(consoles, [])
                    else:
                        probe.main()
                        self.assertEqual(
                            json.loads((out / "results.json").read_text())[0]["sha256"], digest
                        )
                    self.assertEqual(len(installs), 1)
                    self.assertEqual(installs[0][-1], wheel.as_uri() + "#sha256=" + digest)
                    self.assertIn("--require-hashes", installs[0])
                    self.assertIn("--force-reinstall", installs[0])
