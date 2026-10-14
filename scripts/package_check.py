"""Build wheels twice and install into a fresh environment outside the source tree."""

import hashlib
import importlib.metadata
import io
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

# Optimized execution removes the assertions that establish this evidence.
if sys.flags.optimize:
    raise SystemExit("package_check_requires_assertions")

ROOT = Path(__file__).resolve().parents[1]


SOURCE_SUFFIXES = (".py", ".pxd", ".json")
WINDOWS_DEVICE_NAMES = frozenset(
    ("CON", "PRN", "AUX", "NUL")
    + tuple(prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³")
)


def reproduction_workspace(**kwargs):
    # Installed payload probes run this file with -I, without sibling imports.
    # Only the build orchestrator needs the shared workspace lifecycle.
    if __package__:
        from .reproduce import reproduction_workspace as workspace
    else:
        from reproduce import reproduction_workspace as workspace
    return workspace(**kwargs)


def wheel_paths(directory):
    """Admit wheel inventories before payload reads or installed consumers."""
    reject_path_redirect(directory, "wheel_artifacts_changed")
    if not directory.is_dir():
        raise ValueError("wheel_artifacts_changed")
    paths = sorted(directory.glob("*.whl"))
    for path in paths:
        reject_path_redirect(path, "wheel_artifacts_changed")
        if not path.is_file():
            raise ValueError("wheel_artifacts_changed")
    return paths


def reject_path_redirect(path, reason):
    # is_symlink alone misses Windows junctions. Match the verifier's reparse
    # admission using lstat, available at the supported Python 3.9 floor.
    # This assumes a stable tree, not protection from concurrent replacement.
    try:
        info = path.lstat()
    except FileNotFoundError:
        return  # The caller retains its existing missing-path error.
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
    ):
        raise ValueError(reason)


def snapshot_source_payload(root, package_name="aethron"):
    payload = {}
    package = root / package_name
    reject_path_redirect(package, "invalid_source_payload_file")
    if not package.exists():
        raise ValueError("empty_source_payload")

    def unreadable(error):
        raise error

    for directory, directories, files in os.walk(package, onerror=unreadable):
        for name in directories:
            path = Path(directory) / name
            reject_path_redirect(path, "invalid_source_payload_file")
            if path.suffix.casefold() in SOURCE_SUFFIXES:
                raise ValueError("invalid_source_payload_file")
        for name in files:
            path = Path(directory) / name
            # Match wheel admission on every host, preserving the actual name
            # and bytes for both prebuild and installed-payload comparisons.
            if path.suffix.casefold() in SOURCE_SUFFIXES:
                reject_path_redirect(path, "invalid_source_payload_file")
                if not path.is_file():
                    raise ValueError("invalid_source_payload_file")
                payload[path.relative_to(root).as_posix()] = path.read_bytes()
    if not payload:
        raise ValueError("empty_source_payload")
    return payload


def validate_source_payload(wheel_bytes, payload, package_name="aethron"):
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
        sources = {}
        file_destinations = set()
        directory_destinations = set()
        for member in wheel.infolist():
            # ZipInfo truncates filename at NUL; inspecting only that normalized
            # spelling would silently admit a different original archive name.
            if "\x00" in member.orig_filename:
                raise ValueError("wheel_source_payload_mismatch")
            name = member.filename
            # Check every record before filtering package sources: an alias can
            # fall outside that prefix yet normalize into it during installation.
            # Accept canonical relative ZIP paths on every host, including explicit
            # directory records, without guessing the installer's normalization.
            # Trailing dots/spaces in any component are not portable Windows
            # names and can alias a verified destination after installation.
            # Reserved punctuation and ASCII controls are also invalid ordinary
            # Windows filenames. Reject on every host, including resources and
            # directories, rather than certify a Linux-only install as portable.
            path = name[:-1] if member.is_dir() else name
            if any(ord(character) < 32 or character in '<>:"\\|?*' for character in path) or any(
                not part or part.endswith((".", " ")) for part in path.split("/")
            ):
                raise ValueError("wheel_source_payload_mismatch")
            # Windows reserves device names in every directory, even with an
            # extension. Check the archive on every build host before any reads
            # or installation; a resource can resolve to a device instead of a
            # regular file. Explicit directory records obey the same rule.
            if any(
                part.split(".", 1)[0].upper() in WINDOWS_DEVICE_NAMES for part in path.split("/")
            ):
                raise ValueError("wheel_source_payload_mismatch")
            parts = name.split("/", 2)
            # Installers spread these records into the same import directories
            # as root members. Compare destination names and reject collisions
            # before installation, regardless of ZIP record order or contents.
            if (
                len(parts) == 3
                and parts[0].endswith(".data")
                and parts[1] in ("purelib", "platlib")
            ):
                name = parts[2]
            # Every ancestor is an implicit directory, even without a ZIP
            # directory record. A destination cannot be both a file and a
            # directory, in either record order or across spread layouts.
            folded_name = name.casefold()
            destination = folded_name.rstrip("/")
            components = destination.split("/")
            directories = {"/".join(components[:i]) for i in range(1, len(components))}
            if member.is_dir() and destination:
                directories.add(destination)
            if directories & file_destinations:
                raise ValueError("wheel_source_payload_mismatch")
            if not member.is_dir():
                if destination in file_destinations or destination in directory_destinations:
                    raise ValueError("wheel_source_payload_mismatch")
                file_destinations.add(destination)
            directory_destinations.update(directories)
            # These distributions do not declare site-level path configuration.
            # A .pth file here can execute at interpreter startup (even with -I),
            # before the installed-source probe gets control. Reject both code
            # and path-only files without interpreting their contents. Nested
            # package resources and directory records are not startup hooks.
            if not member.is_dir() and "/" not in name and name.casefold().endswith(".pth"):
                raise ValueError("wheel_source_payload_mismatch")
            # Python also imports sitecustomize (even with -I) and, when user
            # sites are enabled, usercustomize before the consumer can inspect
            # installed sources. Neither distribution declares these hooks.
            # Reserve their top-level package names and source/native modules
            # across supported platforms; nested package modules are ordinary
            # sources and still participate in payload parity below.
            top = name.split("/", 1)[0].casefold()
            startup_modules = ("sitecustomize", "usercustomize")
            if top in startup_modules or (
                top.split(".", 1)[0] in startup_modules
                and top.endswith((".py", ".pyc", ".so", ".pyd"))
            ):
                raise ValueError("wheel_source_payload_mismatch")
            # These portable source wheels must not supply executable bytecode
            # outside source parity. In particular, a sourceless .pyc module can
            # be imported without appearing in either source manifest. Installers
            # may generate their own caches from the verified sources afterward.
            if not member.is_dir() and name.casefold().endswith(".pyc"):
                raise ValueError("wheel_source_payload_mismatch")
            # Wheels are checked on case-sensitive hosts too. Do not let an
            # uppercase package/suffix bypass admission and overwrite a checked
            # file on a case-insensitive install. Keep exact spelling for parity;
            # case folding only broadens admission and rejects portable collisions.
            if folded_name.startswith(package_name.casefold() + "/") and folded_name.endswith(
                SOURCE_SUFFIXES
            ):
                sources[name] = member
        if sources.keys() != payload.keys():
            raise ValueError("wheel_source_payload_mismatch")
        if any(wheel.read(member) != payload[name] for name, member in sources.items()):
            raise ValueError("wheel_source_payload_mismatch")


def installed_source_manifest(package_name="aethron", distribution="aethron"):
    package = Path(importlib.metadata.distribution(distribution).locate_file(package_name))
    package.resolve().relative_to(Path(sys.prefix).resolve())
    return {
        name: hashlib.sha256(data).hexdigest()
        for name, data in snapshot_source_payload(package.parent, package_name).items()
    }


def verify_installed_source_payload(python, directory, env, source_manifest):
    installed = subprocess.run(
        [str(python), "-I", str(Path(__file__).resolve()), "--installed-payload"],
        cwd=directory,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if json.loads(installed.stdout) != source_manifest:
        raise ValueError("installed_source_payload_mismatch")


def run():
    with reproduction_workspace(prefix="aethron-wheel-") as directory:
        temp = Path(directory)
        source_payload = snapshot_source_payload(ROOT)
        env = dict(os.environ, SOURCE_DATE_EPOCH="1767225600", PYTHONNOUSERSITE="1")
        # Apply the same import environment to builds, installation and consumers.
        # Inherited interpreter paths must not redirect venv or pip execution.
        for variable in ("PYTHONPATH", "PYTHONHOME"):
            env.pop(variable, None)
        for name in ("a", "b"):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--no-isolation",
                    "--wheel",
                    "--outdir",
                    str(temp / name),
                ],
                cwd=ROOT,
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                timeout=180,
            )
        first = wheel_paths(temp / "a")
        second = wheel_paths(temp / "b")
        if len(first) != 1 or len(second) != 1 or first[0].name != second[0].name:
            raise ValueError("wheel_inventory_mismatch")
        a, b = first[0], second[0]
        compared_bytes = a.read_bytes()
        assert compared_bytes == b.read_bytes(), "wheel builds differ"
        validate_source_payload(compared_bytes, source_payload)
        source_manifest = {
            name: hashlib.sha256(data).hexdigest() for name, data in source_payload.items()
        }
        source_payload_sha256 = hashlib.sha256(
            json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        wheel_sha256 = hashlib.sha256(compared_bytes).hexdigest()

        subprocess.run(
            [sys.executable, "-m", "venv", str(temp / "consumer")],
            env=env,
            check=True,
            timeout=180,
        )
        python = temp / "consumer" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                "--require-hashes",
                a.resolve().as_uri() + "#sha256=" + wheel_sha256,
            ],
            cwd=temp,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=180,
        )
        # Match edge packaging: --no-deps does not establish compatible installed
        # requirements. Let pip check active markers/versions offline before any
        # consumer runs; this is not an extras-completeness or security audit.
        subprocess.run(
            [str(python), "-I", "-m", "pip", "check"],
            cwd=temp,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        verify_installed_source_payload(python, temp, env, source_manifest)
        console = python.with_name("aethron.exe" if os.name == "nt" else "aethron")
        help_result = subprocess.run(
            [str(console), "--help"],
            cwd=temp,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert help_result.stdout.strip(), "console help is empty"
        result = subprocess.run(
            [str(python), "-I", "-m", "aethron", "demo"],
            cwd=temp,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(rows) == 22
        person = next(r["result"] for r in rows if r["scenario"] == "person-zero-visible-thermal")
        assert person["recommendation"]["action"] == "STOP"
        assert next(c for c in person["claims"] if c["capability"] == "human_presence")[
            "sources"
        ] == ["thermal_person"]
        temporal = subprocess.run(
            [
                str(python),
                "-I",
                "-m",
                "aethron",
                "replay",
                str(ROOT / "examples/temporal-blackout.jsonl"),
            ],
            cwd=temp,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        tracked = [json.loads(line) for line in temporal.stdout.splitlines()]
        assert len(tracked) == 24
        assert len({r["tracks"][0]["id"] for r in tracked}) == 1
        assert tracked[-1]["tracks"][0]["sources"] == ["depth", "lwir", "radar"]
        # Consumer success cannot qualify an installation it changed. Compare
        # against the original source snapshot again, in a fresh interpreter.
        verify_installed_source_payload(python, temp, env, source_manifest)
        # Consumers must not invalidate the artifacts qualified by the comparison.
        # Keep the original digest; never re-label replacement bytes as verified.
        for wheel in (a, b):
            if wheel_paths(wheel.parent) != [wheel]:
                raise ValueError("wheel_artifacts_changed")
            if wheel.read_bytes() != compared_bytes:
                raise ValueError("wheel_artifacts_changed")
        print(
            json.dumps(
                {
                    "wheel": a.name,
                    "sha256": wheel_sha256,
                    "byte_identical": True,
                    "isolated_install": True,
                    "console_wrapper": True,
                    "dependency_installation": False,
                    "source_payload_files": len(source_manifest),
                    "source_payload_sha256": source_payload_sha256,
                    "installed_source_payload": True,
                }
            )
        )


if __name__ == "__main__":
    if sys.argv[1:] == ["--installed-payload"]:
        print(json.dumps(installed_source_manifest(), sort_keys=True))
    elif sys.argv[1:] == ["--installed-edge-payload"]:
        print(json.dumps(installed_source_manifest("aethron_edge", "aethron-edge"), sort_keys=True))
    else:
        run()
