"""Build wheels twice and install into a fresh environment outside the source tree."""

import base64
import configparser
import csv
import email.parser
import email.policy
import hashlib
import importlib.metadata
import io
import json
import os
import re
import stat
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

# Optimized execution removes the assertions that establish this evidence.
if sys.flags.optimize:
    raise SystemExit("package_check_requires_assertions")

ROOT = Path(__file__).resolve().parents[1]


SOURCE_SUFFIXES = (".py", ".pxd", ".json")
# Release launcher contracts from the two projects' [project.scripts]. A
# declaration change must update admission as well as installed-launcher tests.
CONSOLE_SCRIPTS = {
    "aethron": {"aethron": "aethron.__main__:main"},
    "aethron_edge": {"aethron-edge": "aethron_edge.cli:main"},
}
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


def packaging_environment():
    """Use only the verifier's explicit pip inputs in child processes."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("PIP_") and name.upper() not in ("PYTHONPATH", "PYTHONHOME")
    }
    # --no-index alone does not disable extra find-links/requirements or install
    # destinations. --isolated still reads site/global configuration. Disable
    # all config files using pip's documented null-device setting, and remove
    # inherited option variables without mutating the caller's environment.
    env.update(
        SOURCE_DATE_EPOCH="1767225600",
        PYTHONNOUSERSITE="1",
        PIP_CONFIG_FILE=os.devnull,
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    return env


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


def project_metadata(root):
    """Read these static projects without importing build dependencies in probes."""
    # Keep build-only dependencies out of isolated installed-source probes.
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.9/3.10 build tools already pin tomli.
        import tomli as tomllib
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if not isinstance(project, dict) or not isinstance(project.get("dynamic", []), list):
        raise ValueError("invalid_project_metadata")
    return project


def project_string(root, field):
    """Read a static string declaration from these two source projects."""
    reason = "invalid_project_" + field.replace("-", "_")
    try:
        project = project_metadata(root)
        value = project[field]
        dynamic = project.get("dynamic", [])
        if not isinstance(value, str) or not isinstance(dynamic, list) or field in dynamic:
            raise ValueError(reason)
        return value
    except (KeyError, TypeError, ValueError):
        raise ValueError(reason) from None


def project_version(root):
    """Snapshot the static version declared by these two source projects."""
    from packaging.version import Version

    try:
        return Version(project_string(root, "version"))
    except ValueError:
        raise ValueError("invalid_project_version") from None


def project_requires_python(root):
    """Snapshot Python compatibility, without using the build host's version."""
    from packaging.specifiers import SpecifierSet

    try:
        return SpecifierSet(project_string(root, "requires-python"))
    except ValueError:
        raise ValueError("invalid_project_requires_python") from None


def dependency_contract(requirements, extras):
    """Compare declarations without evaluating markers on the build host."""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    parsed = []
    for value in requirements:
        if not isinstance(value, str):
            raise ValueError("invalid_dependency")
        requirement = Requirement(value)
        requirement.extras = {canonicalize_name(extra) for extra in requirement.extras}
        parsed.append(requirement)
    normalized_extras = []
    for extra in extras:
        if not isinstance(extra, str):
            raise ValueError("invalid_extra")
        normalized_extras.append(canonicalize_name(extra, validate=True))
    # Reordering is harmless; dropped, injected or duplicated entries are not.
    return Counter(parsed), Counter(normalized_extras)


def project_dependencies(root):
    """Snapshot base and optional requirements before invoking the build backend."""
    from packaging.markers import Marker
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    try:
        project = project_metadata(root)
        if any(
            field in project.get("dynamic", [])
            for field in ("dependencies", "optional-dependencies")
        ):
            raise ValueError("dynamic_dependencies")
        dependencies = project.get("dependencies", [])
        optional = project.get("optional-dependencies", {})
        if not isinstance(dependencies, list) or not isinstance(optional, dict):
            raise ValueError("invalid_dependencies")
        requirements = list(dependencies)
        extras = []
        for extra, values in optional.items():
            normalized = canonicalize_name(extra, validate=True)
            if normalized in extras or not isinstance(values, list):
                raise ValueError("invalid_optional_dependencies")
            extras.append(normalized)
            for value in values:
                if not isinstance(value, str):
                    raise ValueError("invalid_dependency")
                requirement = Requirement(value)
                marker = f"extra == '{normalized}'"
                if requirement.marker is not None:
                    marker = f"({requirement.marker}) and {marker}"
                requirement.marker = Marker(marker)
                requirements.append(str(requirement))
        return dependency_contract(requirements, extras)
    except (KeyError, TypeError, ValueError):
        raise ValueError("invalid_project_dependencies") from None


def validate_source_payload(
    wheel_bytes,
    payload,
    package_name="aethron",
    *,
    wheel_filename=None,
    expected_project_version=None,
    expected_requires_python=None,
    expected_dependencies=None,
):
    expected_version = None
    if wheel_filename is not None:
        # The installer can accept a filename version different from METADATA
        # and its dist-info directory. Bind present metadata to the artifact
        # actually selected for installation, using the build tools' parser.
        from packaging.utils import canonicalize_name, parse_wheel_filename

        try:
            distribution, expected_version, _, _ = parse_wheel_filename(wheel_filename)
        except ValueError:
            raise ValueError("wheel_source_payload_mismatch") from None
        if distribution != canonicalize_name(package_name):
            raise ValueError("wheel_source_payload_mismatch")
    if expected_project_version is not None and expected_version != expected_project_version:
        raise ValueError("wheel_source_payload_mismatch")
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
        sources = {}
        file_destinations = set()
        directory_destinations = set()
        entry_points = []
        distribution_metadata = []
        distribution_records = []
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
            # These distributions declare entry-point wrappers, not bundled
            # scripts. Script payloads bypass package-source parity and can
            # overwrite environment tools before an installed probe runs.
            # The data scheme can also reach the standard script directories.
            # Reserve those prefix destinations across hosts, while allowing
            # nested documentation/resources named bin or scripts.
            if len(parts) == 3 and parts[0].endswith(".data"):
                data_parts = parts[2].split("/")
                # The data scheme is relative to the environment prefix.
                # Environment configuration belongs to the environment creator.
                # pyvenv.cfg changes interpreter isolation; pip.conf/pip.ini
                # change subsequent installer behavior even with --isolated.
                # Reserve the destination across hosts, including directory
                # aliases, while permitting nested documentation examples.
                if parts[1] == "data" and data_parts[0].casefold() in (
                    "pyvenv.cfg",
                    "pip.conf",
                    "pip.ini",
                ):
                    raise ValueError("wheel_source_payload_mismatch")
                if parts[1] == "scripts" or (
                    parts[1] == "data"
                    and len(data_parts) > 1
                    and data_parts[0].casefold() in ("bin", "scripts")
                ):
                    raise ValueError("wheel_source_payload_mismatch")
            # The data scheme installs relative to the environment prefix, so
            # it can write into site-packages too (including via Lib/lib64).
            # These source-wheel checks must not treat such writes as opaque
            # resources and bypass source parity or startup-hook admission.
            # Reserve these directory components across hosts; import payloads
            # belong in the root, purelib or platlib layouts checked below.
            # This is not a resolver for arbitrary custom installation schemes.
            if (
                len(parts) == 3
                and parts[0].endswith(".data")
                and parts[1] == "data"
                and {part.casefold() for part in parts[2].split("/")[:-1]}
                & {"site-packages", "dist-packages"}
            ):
                raise ValueError("wheel_source_payload_mismatch")
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
            # Installers generate executable wrappers from this metadata even
            # when no .data/scripts payload exists. Inspect the installed root,
            # including spread layouts, but leave nested examples as resources.
            if (
                len(components) == 2
                and components[0].endswith(".dist-info")
                and components[1] == "entry_points.txt"
            ):
                if member.is_dir() or member.file_size > 65536:
                    raise ValueError("wheel_source_payload_mismatch")
                entry_points.append(member)
            if (
                len(components) == 2
                and components[0].endswith(".dist-info")
                and components[1] == "metadata"
            ):
                # Bound parsing for these source wheels (including their README
                # descriptions); this is not a general metadata format limit.
                if member.is_dir() or member.file_size > 1048576:
                    raise ValueError("wheel_source_payload_mismatch")
                distribution_metadata.append(member)
            if (
                len(components) == 2
                and components[0].endswith(".dist-info")
                and components[1] == "record"
            ):
                if member.is_dir() or member.file_size > 1048576:
                    raise ValueError("wheel_source_payload_mismatch")
                distribution_records.append(member)
            # These distributions do not declare site-level path configuration.
            # A .pth file here can execute at interpreter startup (even with -I),
            # before the installed-source probe gets control. Reject both code
            # and path-only files without interpreting their contents. Nested
            # package resources and directory records are not startup hooks.
            if not member.is_dir() and "/" not in name and name.casefold().endswith(".pth"):
                raise ValueError("wheel_source_payload_mismatch")
            top = name.split("/", 1)[0].casefold()
            # Distribution metadata affects dependency/version discovery even
            # when all verified Python sources remain unchanged. Spread layouts
            # can overwrite another distribution's metadata without presenting
            # a second dist-info directory at the wheel root. Each source wheel
            # owns only its matching dist-info namespace and emits no legacy
            # egg-info. Nested examples are not discovery roots. This checks
            # destination ownership; present METADATA identities are checked below.
            if top.endswith(".egg-info") or (
                top.endswith(".dist-info") and top.split("-", 1)[0] != package_name.casefold()
            ):
                raise ValueError("wheel_source_payload_mismatch")
            # Python also imports sitecustomize (even with -I) and, when user
            # sites are enabled, usercustomize before the consumer can inspect
            # installed sources. Neither distribution declares these hooks.
            # Reserve their top-level package names and source/native modules
            # across supported platforms; nested package modules are ordinary
            # sources and still participate in payload parity below.
            startup_modules = ("sitecustomize", "usercustomize")
            if top in startup_modules or (
                top.split(".", 1)[0] in startup_modules
                and top.endswith((".py", ".pyc", ".so", ".pyd"))
            ):
                raise ValueError("wheel_source_payload_mismatch")
            # These distributions each own one import package. Foreign source
            # or extension modules can overwrite or shadow another distribution
            # while leaving this package's manifest unchanged. Reserve .so/.pyd
            # across hosts, including ABI-tagged names; host EXTENSION_SUFFIXES
            # alone would miss other supported platforms. This is ownership
            # admission, not binary parity for the package's own native modules.
            # Check root and spread destinations
            # before any payload reads; metadata and non-import data schemes
            # may still contain ordinary Python examples/resources.
            if (
                not member.is_dir()
                and folded_name.endswith((".py", ".so", ".pyd"))
                and not folded_name.startswith(package_name.casefold() + "/")
                and not top.endswith((".dist-info", ".data"))
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
        if any(
            len(records) > 1
            for records in (entry_points, distribution_metadata, distribution_records)
        ):
            raise ValueError("wheel_source_payload_mismatch")
        if (
            expected_requires_python is not None or expected_dependencies is not None
        ) and not distribution_metadata:
            raise ValueError("wheel_source_payload_mismatch")
        for member in distribution_records:
            # pip retains unrecognized RECORD paths in the installed removal
            # inventory. A wheel must not claim files outside its admitted ZIP
            # members, even if its own source bytes match perfectly. Check exact
            # archive names (before spreading), not normalized installed names.
            # A present inventory must also cover every archive file except
            # its adjacent wheel signatures, which are added after RECORD.
            # Explicit ZIP directories and nested signature examples are not
            # signature files. Preserve exact archive names for this check.
            files = {item.filename: item for item in wheel.infolist() if not item.is_dir()}
            seen = set()
            try:
                contents = wheel.read(member).decode("utf-8")
                for row in csv.reader(io.StringIO(contents, newline=""), strict=True):
                    if len(row) != 3 or row[0] not in files or row[0] in seen:
                        raise ValueError("wheel_source_payload_mismatch")
                    seen.add(row[0])
                    if row[0] == member.filename and (row[1] or row[2]):
                        raise ValueError("wheel_source_payload_mismatch")
                    validate_record_integrity(wheel, files[row[0]], row[1], row[2])
            except (UnicodeError, csv.Error):
                raise ValueError("wheel_source_payload_mismatch") from None
            signatures = {member.filename + ".jws", member.filename + ".p7s"}
            if files.keys() - signatures - seen:
                raise ValueError("wheel_source_payload_mismatch")
        for member in distribution_metadata:
            # Reuse the inventory tool's email-header interpretation. A matching
            # dist-info directory alone cannot establish distribution identity.
            # Multiple Name headers are ambiguous; normalize valid project names
            # per PyPA, without decoding email encoded words as package names.
            try:
                metadata = email.parser.Parser(policy=email.policy.compat32).parsestr(
                    wheel.read(member).decode("utf-8"), headersonly=True
                )
            except UnicodeError:
                raise ValueError("wheel_source_payload_mismatch") from None
            names = metadata.get_all("Name", [])
            if (
                metadata.defects
                or len(names) != 1
                or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", names[0])
                or re.sub(r"[-_.]+", "_", names[0].lower()) != package_name.casefold()
            ):
                raise ValueError("wheel_source_payload_mismatch")
            # Version discovery trusts METADATA, not the directory's version.
            # Bind the two before installation, including spread metadata. Use
            # the existing build-tool dependency for PEP 440 equivalence rather
            # than maintaining a second version parser. This lazy import keeps
            # installed-source probes usable in dependency-free core venvs.
            from packaging.version import Version

            versions = metadata.get_all("Version", [])
            if len(versions) != 1:
                raise ValueError("wheel_source_payload_mismatch")
            directory = member.filename.rsplit("/", 2)[-2]
            directory_version = directory[: -len(".dist-info")].partition("-")[2]
            try:
                version = Version(versions[0])
                same_version = version == Version(directory_version) and (
                    expected_version is None or version == expected_version
                )
            except ValueError:
                # Includes Python's integer digit limit for oversized segments.
                raise ValueError("wheel_source_payload_mismatch") from None
            if not same_version:
                raise ValueError("wheel_source_payload_mismatch")
            if expected_requires_python is not None:
                # Testing only the current interpreter misses changed support
                # ranges. Bind the declaration itself before installation,
                # allowing normalized specifier spelling/order, not arbitrary
                # logical rewrites. Build tools already supply this parser.
                from packaging.specifiers import SpecifierSet

                requirements = metadata.get_all("Requires-Python", [])
                if len(requirements) != 1:
                    raise ValueError("wheel_source_payload_mismatch")
                try:
                    same_requirement = SpecifierSet(requirements[0]) == expected_requires_python
                except ValueError:
                    raise ValueError("wheel_source_payload_mismatch") from None
                if not same_requirement:
                    raise ValueError("wheel_source_payload_mismatch")
            if expected_dependencies is not None:
                try:
                    actual_dependencies = dependency_contract(
                        metadata.get_all("Requires-Dist", []),
                        metadata.get_all("Provides-Extra", []),
                    )
                except ValueError:
                    raise ValueError("wheel_source_payload_mismatch") from None
                if actual_dependencies != expected_dependencies:
                    raise ValueError("wheel_source_payload_mismatch")
        for member in entry_points:
            parser = configparser.ConfigParser(interpolation=None, delimiters=("=",))
            parser.optionxform = str
            try:
                parser.read_string(wheel.read(member).decode("utf-8"))
            except (UnicodeError, configparser.Error):
                raise ValueError("wheel_source_payload_mismatch") from None
            if (
                parser.defaults()
                or parser.sections() != ["console_scripts"]
                or dict(parser.items("console_scripts")) != CONSOLE_SCRIPTS.get(package_name)
            ):
                raise ValueError("wheel_source_payload_mismatch")
        if sources.keys() != payload.keys():
            raise ValueError("wheel_source_payload_mismatch")
        if any(wheel.read(member) != payload[name] for name, member in sources.items()):
            raise ValueError("wheel_source_payload_mismatch")


def validate_record_integrity(wheel, member, declared_hash, declared_size):
    """Check supplied RECORD fields against uncompressed archive contents."""
    if declared_size and (
        not re.fullmatch(r"[0-9]+", declared_size)
        or (declared_size.lstrip("0") or "0") != str(member.file_size)
    ):
        raise ValueError("wheel_source_payload_mismatch")
    if not declared_hash:
        return
    algorithm, separator, expected = declared_hash.partition("=")
    # Portable fixed-length stdlib digests of at least 256 bits. Do not let
    # platform OpenSSL aliases or variable-length SHAKE change admission.
    if not separator or algorithm not in (
        "sha256",
        "sha384",
        "sha512",
        "sha3_256",
        "sha3_384",
        "sha3_512",
        "blake2b",
        "blake2s",
    ):
        raise ValueError("wheel_source_payload_mismatch")
    digest = hashlib.new(algorithm)
    # Hash resources as well as package sources, without another full payload
    # allocation. ZIP reads also check the member's CRC at end-of-stream.
    with wheel.open(member) as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    actual = base64.urlsafe_b64encode(digest.digest()).rstrip(b"=").decode("ascii")
    if expected != actual:
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
        version = project_version(ROOT)
        requires_python = project_requires_python(ROOT)
        dependencies = project_dependencies(ROOT)
        env = packaging_environment()
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
        validate_source_payload(
            compared_bytes,
            source_payload,
            wheel_filename=a.name,
            expected_project_version=version,
            expected_requires_python=requires_python,
            expected_dependencies=dependencies,
        )
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
