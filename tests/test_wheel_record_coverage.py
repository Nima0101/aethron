"""Present wheel inventories must cover archive files, not just valid subsets."""

import base64
import csv
import hashlib
import io
import unittest
import zipfile

from scripts import package_check


def inventory_wheel(package, layout="", omit=(), signatures=False):
    payload = {f"{package}/module.py": b"VALUE = 1\n"}
    metadata = layout + f"{package}-0.2.0.dist-info/"
    record = metadata + "RECORD"
    files = {
        **payload,
        metadata + "METADATA": f"Name: {package}\nVersion: 0.2.0\n".encode(),
        metadata + "WHEEL": b"Wheel-Version: 1.0\n",
        f"{package}/resources/caf\u00e9,notes.txt": b"ordinary resource",
        f"{package}/examples/RECORD.jws": b"not a wheel signature",
        f"{package}/examples/RECORD.p7s": b"not a wheel signature",
        f"{package}-0.2.0.data/data/share/license.txt": b"license fixture",
    }
    rows = io.StringIO(newline="")
    writer = csv.writer(rows)
    for name, data in files.items():
        if name not in omit:
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
            writer.writerow((name, "sha256=" + digest.decode(), str(len(data))))
    if record not in omit:
        writer.writerow((record, "", ""))
    files[record] = rows.getvalue().encode()
    if signatures:
        files[record + ".jws"] = b"signature fixture; authenticity not evaluated"
        files[record + ".p7s"] = b"signature fixture; authenticity not evaluated"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as wheel:
        wheel.writestr(f"{package}/resources/", b"")
        for name, data in files.items():
            wheel.writestr(name, data)
    return output.getvalue(), payload


class WheelRecordCoverage(unittest.TestCase):
    def test_complete_inventory_and_unlisted_signatures_pass(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for signatures in (False, True):
                    with self.subTest(package=package, layout=layout, signatures=signatures):
                        raw, payload = inventory_wheel(package, layout, signatures=signatures)
                        package_check.validate_source_payload(raw, payload, package)

    def test_missing_source_metadata_resource_or_self_row_rejects(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                metadata = layout + f"{package}-0.2.0.dist-info/"
                for omitted in (
                    f"{package}/module.py",
                    metadata + "METADATA",
                    metadata + "WHEEL",
                    metadata + "RECORD",
                    f"{package}/resources/caf\u00e9,notes.txt",
                    f"{package}/examples/RECORD.jws",
                    f"{package}/examples/RECORD.p7s",
                    f"{package}-0.2.0.data/data/share/license.txt",
                ):
                    with self.subTest(package=package, layout=layout, omitted=omitted):
                        raw, payload = inventory_wheel(package, layout, omit=(omitted,))
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(raw, payload, package)

    def test_empty_inventory_rejects(self):
        raw, payload = inventory_wheel("aethron")
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(output, "w") as wheel:
            for member in source.infolist():
                data = b"" if member.filename.endswith("/RECORD") else source.read(member)
                wheel.writestr(member, data)
        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
            package_check.validate_source_payload(output.getvalue(), payload)
