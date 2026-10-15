"""Build valid RECORD fields for inert wheel fixtures, independent of admission."""

import base64
import csv
import hashlib
import io
import zipfile


def record_row(name, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return name, "sha256=" + digest, str(len(data))


def refresh_record(raw):
    """Refresh hashes after deliberate metadata edits, preserving inventory paths."""
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as before, zipfile.ZipFile(output, "w") as after:
        for member in before.infolist():
            data = before.read(member)
            if member.filename.endswith(".dist-info/RECORD"):
                rows = []
                for name, digest, size in csv.reader(io.StringIO(data.decode())):
                    if name != member.filename and name in before.namelist():
                        rows.append(record_row(name, before.read(name)))
                    else:
                        rows.append((name, digest, size))
                record = io.StringIO(newline="")
                csv.writer(record).writerows(rows)
                data = record.getvalue().encode()
            after.writestr(member, data)
    return output.getvalue()
