"""Explicit test-only RTSP fixture installation, pinned release and checksums."""

import hashlib
import io
import platform
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.21.1"


def run():
    system = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}[platform.system()]
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "AMD64": "amd64"}[
        platform.machine()
    ]
    if system == "linux" and arch == "arm64":
        arch = "arm64v8"
    suffix = "zip" if system == "windows" else "tar.gz"
    name = f"mediamtx_v{VERSION}_{system}_{arch}.{suffix}"
    base = f"https://github.com/bluenviron/mediamtx/releases/download/v{VERSION}/"
    with urllib.request.urlopen(base + "checksums.sha256", timeout=30) as response:
        checks = response.read(65536).decode()
    expected = {line.split()[1].lstrip("*"): line.split()[0] for line in checks.splitlines()}
    with urllib.request.urlopen(base + name, timeout=60) as response:
        blob = response.read(64 * 1024 * 1024 + 1)
    if len(blob) > 64 * 1024 * 1024 or hashlib.sha256(blob).hexdigest() != expected[name]:
        raise ValueError("fixture_integrity")
    destination = ROOT / "build/ecosystem-phase1/tools"
    destination.mkdir(parents=True, exist_ok=True)
    executable = "mediamtx.exe" if system == "windows" else "mediamtx"
    if suffix == "zip":
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            data = archive.read(executable)
    else:
        with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
            data = archive.extractfile(executable).read()
    path = destination / executable
    path.write_bytes(data)
    path.chmod(0o755)
    print(
        f"Verified test-only MediaMTX {VERSION} {system}/{arch}: {hashlib.sha256(blob).hexdigest()}"
    )


if __name__ == "__main__":
    run()
