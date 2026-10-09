"""Offline Ed25519 manifests and transactional version-directory activation."""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .._startup_trace import mark
from ..config import strict_json
from ._regular_file import regular_reader
from ._store_lock import exclusive_store


def digest(path):
    with regular_reader(path, 512 * 1024 * 1024) as (stream, remaining):
        buffer = bytearray(min(max(remaining, 1), 256 * 1024))
        view = memoryview(buffer)
        result = hashlib.sha256()
        # Bound both allocation and reads to the inspected size, with one EOF byte.
        while remaining:
            count = stream.readinto(view[: min(remaining, len(buffer))])
            if not count:
                raise ValueError("invalid_bundle")
            result.update(view[:count])
            remaining -= count
        if stream.read(1):
            raise ValueError("invalid_bundle")
    return result.hexdigest()


def _inventory(path):
    def inaccessible(error):
        raise error

    actual = set()
    # Unlike Path.rglob, walk's onerror lets incomplete traversal fail closed.
    for directory, directories, files in os.walk(path, followlinks=False, onerror=inaccessible):
        # Normalize the display prefix once; file/type trust is still checked per entry.
        prefix = Path(os.path.relpath(directory, path)).as_posix()
        prefix = "" if prefix == "." else prefix + "/"
        for name in directories + files:
            item = os.path.join(directory, name)
            mode = os.lstat(item).st_mode
            if stat.S_ISREG(mode):
                actual.add(prefix + name)
            elif not stat.S_ISDIR(mode):
                # Never hide directory links, dangling links or special files.
                raise ValueError("invalid_bundle")
    return actual


def verify_bundle(path: Path, public_key: Path):
    try:
        if (
            path.is_symlink()
            or (path / "manifest.json").is_symlink()
            or (path / "manifest.sig").is_symlink()
        ):
            raise ValueError()
        manifest_path = path / "manifest.json"
        limit = 2 * 1024 * 1024
        with regular_reader(manifest_path, limit) as (stream, _):
            raw = stream.read(limit + 1)
        manifest = strict_json(raw, limit)
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
        # Reject malformed entries before crypto or any payload reads. Retain only
        # parsed names, never filesystem trust: ancestors/leaves are checked below.
        entries = []
        for name, expected in files.items():
            relative = Path(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not re.fullmatch(r"[a-zA-Z0-9_./-]{1,180}", name)
                or not isinstance(expected, str)
                or not re.fullmatch("[a-f0-9]{64}", expected)
            ):
                raise ValueError()
            entries.append((relative, expected))
        signature_path = path / "manifest.sig"
        with regular_reader(signature_path, 64) as (stream, size):
            if size != 64:
                raise ValueError()
            signature = stream.read(65)
        if len(signature) != 64:
            raise ValueError()
        mark("bundle_signature_start")
        # OpenSSL Ed25519 needs a seekable input. Verify a private copy of the
        # exact parsed bytes, never a second read of a caller-controlled path.
        with tempfile.TemporaryDirectory(prefix="aethron-verify-") as temporary:
            snapshot = Path(temporary)
            (snapshot / "manifest.json").write_bytes(raw)
            (snapshot / "manifest.sig").write_bytes(signature)
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
                    str(snapshot / "manifest.json"),
                    "-sigfile",
                    str(snapshot / "manifest.sig"),
                ],
                capture_output=True,
                check=False,
                timeout=5,
            )
        if result.returncode:
            raise ValueError()
        mark("bundle_signature_done")
        root = os.fspath(path)
        for relative, expected in entries:
            # Check every ancestor for every file, without caching path trust.
            # The leaf's lstat in digest rejects links and non-regular files.
            parent = root
            if os.path.islink(parent):
                raise ValueError()
            for part in relative.parts[:-1]:
                parent = os.path.join(parent, part)
                if os.path.islink(parent):
                    raise ValueError()
            if digest(path / relative) != expected:
                raise ValueError()
        mark("bundle_hashes_done")
        actual = _inventory(path)
        if actual != set(files) | {"manifest.json", "manifest.sig"}:
            raise ValueError()
        mark("bundle_inventory_done")
        return manifest
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        raise ValueError("invalid_bundle") from None


def verify_configuration(config, config_path: Path):
    """Bind the actual config and file/model inputs to the verified manifest."""
    if not config.integrity_bundle or not config.trust_root:
        raise ValueError("integrity_required")
    root = Path(config.integrity_bundle).resolve()
    manifest = verify_bundle(root, Path(config.trust_root))
    for telemetry in config.telemetry:
        for name in (telemetry.credential_file, telemetry.clock_policy_file, telemetry.replay_file):
            if name is not None and Path(name).resolve().is_relative_to(root):
                raise ValueError("private_telemetry_state_in_bundle")
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
        with exclusive_store(self.root):
            return self._stage_update(bundle)

    def _stage_update(self, bundle: Path) -> VerifiedCandidate:
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
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return None
        limit = 65536
        try:
            with regular_reader(path, limit, metadata=metadata) as (stream, _):
                state = strict_json(stream.read(limit + 1), limit)
            if (
                not isinstance(state, dict)
                or set(state) != {"slot", "minimum_version"}
                or not isinstance(state["slot"], str)
                or not re.fullmatch(r"[0-9]+-[a-f0-9]{16}", state["slot"])
                or type(state["minimum_version"]) is not int
                or not 1 <= state["minimum_version"] <= 2**31 - 1
            ):
                raise ValueError()
            return state
        except (ValueError, RecursionError):
            raise ValueError("invalid_update_state") from None

    def activate(self, candidate: VerifiedCandidate):
        with exclusive_store(self.root):
            return self._activate(candidate)

    def _activate(self, candidate: VerifiedCandidate):
        if candidate.path.parent.resolve() != self.root:
            raise ValueError("invalid_candidate")
        manifest = verify_bundle(candidate.path, self.public_key)
        old = self._state()
        if old and manifest["version"] < old["minimum_version"]:
            raise ValueError("rollback_rejected")
        state = {"slot": candidate.path.name, "minimum_version": manifest["version"]}
        temporary = None
        try:
            # Exclusive creation avoids following a leftover or substituted scratch link.
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.root, prefix="activate-", suffix=".pending", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(state, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.root / "active.json")
            self._sync()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {"state": "activated", "version": manifest["version"]}

    def recover(self):
        try:
            state = self._state()
            if state is None:
                return {"state": "unprovisioned"}
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
        with exclusive_store(self.root):
            self._factory_reset()

    def _factory_reset(self):
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
