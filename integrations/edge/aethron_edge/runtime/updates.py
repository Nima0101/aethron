"""Offline Ed25519 manifests and transactional version-directory activation."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..config import strict_json


def digest(path):
    h = hashlib.sha256()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("invalid_bundle")
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_bundle(path: Path, public_key: Path):
    try:
        if (
            path.is_symlink()
            or (path / "manifest.json").is_symlink()
            or (path / "manifest.sig").is_symlink()
        ):
            raise ValueError()
        raw = (path / "manifest.json").read_bytes()
        manifest = strict_json(raw, 2 * 1024 * 1024)
        if set(manifest) != {"schema_version", "version", "config_version", "files"}:
            raise ValueError()
        if (
            type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or type(manifest["config_version"]) is not int
            or manifest["config_version"] != 1
            or type(manifest["version"]) is not int
            or not 1 <= manifest["version"] <= 2**31 - 1
        ):
            raise ValueError()
        files = manifest["files"]
        if not isinstance(files, dict) or not 1 <= len(files) <= 8192:
            raise ValueError()
        if (path / "manifest.sig").stat().st_size != 64:
            raise ValueError()
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public_key),
                "-rawin",
                "-in",
                str(path / "manifest.json"),
                "-sigfile",
                str(path / "manifest.sig"),
            ],
            capture_output=True,
            check=False,
            timeout=5,
        )
        if result.returncode:
            raise ValueError()
        for name, expected in files.items():
            relative = Path(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not re.fullmatch(r"[a-zA-Z0-9_./-]{1,180}", name)
            ):
                raise ValueError()
            if any((path / parent).is_symlink() for parent in (relative, *relative.parents)):
                raise ValueError()
            if (
                not isinstance(expected, str)
                or not re.fullmatch("[a-f0-9]{64}", expected)
                or digest(path / relative) != expected
            ):
                raise ValueError()
        actual = {str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()}
        if actual != set(files) | {"manifest.json", "manifest.sig"}:
            raise ValueError()
        return manifest
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise ValueError("invalid_bundle") from None


def verify_configuration(config, config_path: Path):
    """Bind the actual config and file/model inputs to the verified manifest."""
    if not config.integrity_bundle or not config.trust_root:
        raise ValueError("integrity_required")
    root = Path(config.integrity_bundle).resolve()
    manifest = verify_bundle(root, Path(config.trust_root))
    inputs = [config_path]
    for profile in config.profiles:
        if profile.driver in ("replay", "file", "sensor-replay"):
            inputs.append(Path(profile.address))
        if profile.sensor_manifest:
            inputs.append(Path(profile.sensor_manifest))
        if profile.model:
            inputs.append(Path(profile.model))
    for path in inputs:
        try:
            name = str(path.resolve().relative_to(root))
        except ValueError:
            raise ValueError("unsigned_configuration_input") from None
        if name not in manifest["files"]:
            raise ValueError("unsigned_configuration_input")
    return manifest


@dataclass(frozen=True)
class VerifiedCandidate:
    path: Path
    version: int


class UpdateStore:
    def __init__(self, root: Path, public_key: Path):
        if root.is_symlink():
            raise ValueError("invalid_store")
        self.root = root.resolve()
        self.public_key = public_key.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def stage_update(self, bundle: Path) -> VerifiedCandidate:
        manifest = verify_bundle(bundle, self.public_key)
        temporary = Path(tempfile.mkdtemp(prefix="stage-", suffix=".pending", dir=self.root))
        try:
            # Copy only signed files, never archive paths or unlisted executable content.
            for name in [*manifest["files"], "manifest.json", "manifest.sig"]:
                destination = temporary / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(bundle / name, destination)
                destination.chmod((bundle / name).stat().st_mode & 0o755)
                with destination.open("rb") as stream:
                    os.fsync(stream.fileno())
            verify_bundle(temporary, self.public_key)
            final = self.root / (
                str(manifest["version"]) + "-" + digest(temporary / "manifest.json")[:16]
            )
            if final.exists():
                raise ValueError("candidate_exists")
            temporary.replace(final)
            self._sync()
            return VerifiedCandidate(final, manifest["version"])
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def _sync(self):
        if os.name != "nt":
            fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _state(self):
        path = self.root / "active.json"
        return strict_json(path.read_bytes()) if path.exists() else None

    def activate(self, candidate: VerifiedCandidate):
        if candidate.path.parent.resolve() != self.root:
            raise ValueError("invalid_candidate")
        manifest = verify_bundle(candidate.path, self.public_key)
        old = self._state()
        if old and manifest["version"] < old["minimum_version"]:
            raise ValueError("rollback_rejected")
        state = {"slot": candidate.path.name, "minimum_version": manifest["version"]}
        temporary = self.root / "active.pending"
        with temporary.open("w") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.root / "active.json")
        self._sync()
        return {"state": "activated", "version": manifest["version"]}

    def recover(self):
        try:
            state = self._state()
            if state is None:
                return {"state": "unprovisioned"}
            if set(state) != {"slot", "minimum_version"} or not re.fullmatch(
                r"[0-9]+-[a-f0-9]{16}", state["slot"]
            ):
                raise ValueError()
            manifest = verify_bundle(self.root / state["slot"], self.public_key)
            if manifest["version"] < state["minimum_version"]:
                raise ValueError()
            return {
                "state": "ready",
                "version": manifest["version"],
                "path": str(self.root / state["slot"]),
            }
        except (ValueError, OSError, KeyError, TypeError):
            return {"state": "fault"}

    def factory_reset(self):
        # Explicit local-admin operation on this store, never a network endpoint.
        for name in ("active.json", "active.pending"):
            (self.root / name).unlink(missing_ok=True)
        for path in self.root.iterdir():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
        self._sync()


def selected_runtime(store: Path, public_key: Path):
    """Select a fully verified inactive-slot installation on the next boot."""
    state = UpdateStore(store, public_key).recover()
    if state["state"] == "unprovisioned":
        return None
    if state["state"] != "ready":
        raise ValueError("update_store_fault")
    root = Path(state["path"])
    python, config = root / "venv/bin/python", root / "appliance.json"
    if not python.is_file() or not os.access(python, os.X_OK) or not config.is_file():
        raise ValueError("incomplete_runtime_slot")
    return python, config
