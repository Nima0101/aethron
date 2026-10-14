"""Clean clone, exact README quickstart, isolated consumer and two release builds."""

import contextlib
import gzip
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import zlib
from pathlib import Path

# Optimized execution removes assertions used to establish this evidence.
if sys.flags.optimize:
    raise SystemExit("reproduce_requires_assertions")

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ARTIFACTS = frozenset(
    {
        "aethron-0.2.0-source.tar.gz",
        "aethron.pyz",
        "source-manifest.json",
        "sbom.cdx.json",
        "provenance.json",
        "SHA256SUMS",
    }
)


def _require_git_context():
    # Keep the standalone workspace helper usable without repository imports.
    if __package__:
        from .git_context import require_default_git_context
    else:
        from git_context import require_default_git_context

    require_default_git_context(os.environ)


def call(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, check=True, **kw)


def artifact_paths(directory):
    """Admit the complete inventory before reading any artifact payload."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("release_artifacts_changed")
    paths = sorted(directory.iterdir())
    if {path.name for path in paths} != RELEASE_ARTIFACTS:
        raise ValueError("release_artifacts_changed")
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("release_artifacts_changed")
    return paths


def validate_artifacts(directory, manifest):
    observed = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in artifact_paths(directory)
    }
    if observed != manifest:
        raise ValueError("release_artifacts_changed")


def validate_provenance(payload, revision, manifest_sha256):
    """Bind local build declarations, revision and compared source manifest."""

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("release_provenance_invalid")
            result[key] = value
        return result

    try:
        provenance = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        raise ValueError("release_provenance_invalid") from None
    if (
        not isinstance(provenance, dict)
        or provenance.get("source_revision") != revision
        or provenance.get("source_manifest_sha256") != manifest_sha256
        or provenance.get("builder") != "scripts/release.py"
        or provenance.get("evidence") != "local unsigned candidate; not hosted attestation"
        or provenance.get("runtime_dependencies") != "Python 3.9+ standard library"
    ):
        raise ValueError("release_provenance_invalid")
    return provenance


def validate_provenance_sources(provenance, manifest):
    """Bind model and dataset claims to the independently verified source inventory."""
    model = "aethron/models/rules.json"
    data_manifests = {
        name: digest for name, digest in manifest.items() if name.endswith("freeze.json")
    }
    if (
        model not in manifest
        or provenance.get("model_sha256") != manifest[model]
        or provenance.get("data_manifests") != data_manifests
    ):
        raise ValueError("release_provenance_invalid")


def validate_sbom(payload):
    """Check local release declarations, not full CycloneDX conformance or rights."""

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("release_sbom_invalid")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("release_sbom_invalid")

    try:
        bom = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (ValueError, RecursionError):
        raise ValueError("release_sbom_invalid") from None
    if (
        not isinstance(bom, dict)
        or bom.get("bomFormat") != "CycloneDX"
        or bom.get("specVersion") != "1.6"
        or type(bom.get("version")) is not int
        or bom["version"] != 1
        or not isinstance(bom.get("metadata"), dict)
        or not isinstance(bom["metadata"].get("component"), dict)
    ):
        raise ValueError("release_sbom_invalid")
    component = bom["metadata"]["component"]
    if (
        component.get("type") != "application"
        or component.get("name") != "aethron"
        or component.get("version") != "0.2.0"
        or component.get("licenses") != [{"license": {"id": "GPL-3.0-only"}}]
    ):
        raise ValueError("release_sbom_invalid")


def validate_checksums(payload, manifest):
    """Require the builder's canonical checksum inventory for the compared bytes."""
    expected = "".join(
        f"{manifest[name]}  {name}\n" for name in sorted(RELEASE_ARTIFACTS - {"SHA256SUMS"})
    ).encode("utf-8")
    if payload != expected:
        raise ValueError("release_checksums_invalid")


def validate_source_archive(payload, manifest_payload):
    """Inspect the compared TAR bytes without extracting files or following links."""

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate manifest entry")
            result[key] = value
        return result

    try:
        manifest = json.loads(manifest_payload.decode("utf-8"), object_pairs_hook=unique_object)
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError("invalid manifest")
        for name, digest in manifest.items():
            if (
                any(part in ("", ".", "..") for part in name.split("/"))
                or "\\" in name
                or "\x00" in name
                or not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("invalid manifest entry")
        expected = {"aethron-0.2.0/" + name: digest for name, digest in manifest.items()}
        seen = set()
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r:") as archive:
                for member in archive:
                    if not member.isfile() or member.name not in expected or member.name in seen:
                        raise ValueError("invalid archive member")
                    # Content hashes do not cover extraction permissions/ownership.
                    # Enforce the existing release writer's normalized metadata.
                    if (
                        member.mode,
                        member.uid,
                        member.gid,
                        member.uname,
                        member.gname,
                        member.mtime,
                    ) != (0o644, 0, 0, "", "", 0):
                        raise ValueError("invalid archive metadata")
                    seen.add(member.name)
                    digest = hashlib.sha256()
                    with archive.extractfile(member) as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != expected[member.name]:
                        raise ValueError("archive content mismatch")
            # TAR iteration stops at its end marker, before gzip necessarily checks
            # the CRC/size trailer. Drain through EOF, including subsequent members.
            # Only zero padding may follow: a later TAR or arbitrary payload must
            # not escape the manifest inventory checked above.
            for chunk in iter(lambda: compressed.read(1024 * 1024), b""):
                if chunk.strip(b"\x00"):
                    raise ValueError("trailing archive content")
        if seen != expected.keys():
            raise ValueError("incomplete archive")
        return manifest
    except (ValueError, RecursionError, tarfile.TarError, OSError, EOFError, zlib.error):
        raise ValueError("release_source_archive_invalid") from None


def validate_zipapp(payload, manifest):
    """Bind every executable ZIP member to the already validated source manifest."""
    expected = {name: digest for name, digest in manifest.items() if name.startswith("aethron/")}
    try:
        for name in ("LICENSE", "NOTICE"):
            expected[name] = manifest[name]
        expected["__main__.py"] = hashlib.sha256(
            b"from aethron.__main__ import main\nraise SystemExit(main())\n"
        ).hexdigest()
        seen = set()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for member in archive.infolist():
                if (
                    member.filename not in expected
                    or member.filename in seen
                    or member.orig_filename != member.filename
                    or member.is_dir()
                    or member.compress_type != zipfile.ZIP_STORED
                    or member.flag_bits & 1
                    or (
                        member.create_system == 3
                        and stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG)
                    )
                ):
                    raise ValueError("invalid ZIP member")
                seen.add(member.filename)
                digest = hashlib.sha256()
                with archive.open(member) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected[member.filename]:
                    raise ValueError("ZIP content mismatch")
        if seen != expected.keys():
            raise ValueError("incomplete ZIP")
    except (ValueError, KeyError, zipfile.BadZipFile, OSError, EOFError, RuntimeError):
        raise ValueError("release_zipapp_invalid") from None


def validate_source_manifest(clone, revision, manifest):
    """Compare the build's inventory and hashes with the original committed blobs."""
    if __package__:
        from .release import committed_blobs
    else:
        from release import committed_blobs

    expected = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in committed_blobs(revision, root=clone).items()
    }
    if manifest != expected:
        raise ValueError("release_source_manifest_invalid")


def validate_source(clone, revision):
    """Bind sequential checks to one clean revision, excluding ignored build outputs."""
    _require_git_context()
    # These index flags suppress working-tree checks even when status is clean.
    # A complete reproduction clone must keep every tracked file observable.
    entries = subprocess.check_output(
        ["git", "--no-replace-objects", "ls-files", "-v", "-z"], cwd=clone
    )
    if any(entry and not entry.startswith(b"H ") for entry in entries.split(b"\0")):
        raise ValueError("reproduction_source_changed")
    current = subprocess.check_output(
        ["git", "--no-replace-objects", "rev-parse", "HEAD"], cwd=clone, text=True
    ).strip()
    # Compare the original tree named by evidence, as the release builder does.
    dirty = subprocess.check_output(
        ["git", "--no-replace-objects", "status", "--porcelain", "--untracked-files=normal"],
        cwd=clone,
    )
    if current != revision or dirty:
        raise ValueError("reproduction_source_changed")


def _remove_readonly_file(function, path, exc_info):
    """Retry Windows read-only file removal; propagate all other cleanup failures."""
    error = exc_info[1]
    if function not in (os.unlink, os.remove) or not isinstance(error, PermissionError):
        raise error
    mode = os.lstat(path).st_mode
    if not stat.S_ISREG(mode) or mode & stat.S_IWUSR:
        raise error
    os.chmod(path, mode | stat.S_IWUSR)
    function(path)


@contextlib.contextmanager
def reproduction_workspace(*, prefix="aethron-clean-", dir=None):
    """Retain failed runs for diagnosis; only successful runs own automatic cleanup."""
    temporary = tempfile.mkdtemp(prefix=prefix, dir=dir)
    try:
        yield temporary
    except BaseException:
        # Includes evaluation SystemExit and operator interruption.
        print(f"reproduction evidence retained at: {temporary}", file=sys.stderr)
        raise
    else:
        # onerror keeps the callback compatible with the supported Python 3.9.
        shutil.rmtree(temporary, onerror=_remove_readonly_file)


def run():
    _require_git_context()
    # Exercise the clone with the selected interpreter, not caller import overrides.
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    with reproduction_workspace() as temporary:
        root = Path(temporary)
        clone = root / "source"
        call(["git", "clone", "--no-local", str(ROOT), str(clone)], ROOT, capture_output=True)
        revision = subprocess.check_output(
            ["git", "--no-replace-objects", "rev-parse", "HEAD"], cwd=clone, text=True
        ).strip()
        validate_source(clone, revision)
        # Quickstart commands as documented, with the active Python interpreter.
        call([sys.executable, "scripts/verify.py"], clone, env=env)
        evaluation = subprocess.run(
            [sys.executable, "scripts/temporal_evaluate.py", "--out", str(root / "evaluation")],
            cwd=clone,
            check=False,
            env=env,
        )
        with (root / "demo.jsonl").open("w") as stream:
            call([sys.executable, "-m", "aethron", "demo"], clone, stdout=stream, env=env)
        with (root / "result.json").open("w") as stream:
            call(
                [sys.executable, "-m", "aethron", "evaluate", "examples/person-blackout.json"],
                clone,
                stdout=stream,
                env=env,
            )
        with (root / "view.svg").open("w") as stream:
            call(
                [
                    sys.executable,
                    "-m",
                    "aethron",
                    "render",
                    "examples/person-blackout.json",
                    "--now-ms",
                    "1000",
                ],
                clone,
                stdout=stream,
                env=env,
            )
        validate_source(clone, revision)
        probe = clone / "aethron" / "untracked_release_probe.py"
        probe.write_text("# An untracked runtime change must block release.\n", encoding="utf-8")
        refused = subprocess.run(
            [sys.executable, "scripts/release.py", str(root / "refused")],
            cwd=clone,
            capture_output=True,
            check=False,
            env=env,
        )
        assert refused.returncode != 0 and b"clean committed source" in refused.stderr
        probe.unlink()
        call([sys.executable, "scripts/release.py", str(root / "a")], clone, env=env)
        call([sys.executable, "scripts/release.py", str(root / "b")], clone, env=env)
        validate_source(clone, revision)
        a, b = root / "a", root / "b"
        paths_a, paths_b = artifact_paths(a), artifact_paths(b)
        assert [p.name for p in paths_a] == [p.name for p in paths_b]
        artifact_manifest = {}
        for p in paths_a:
            compared = p.read_bytes()
            assert compared == (b / p.name).read_bytes(), p.name
            if p.name == "provenance.json":
                provenance = compared
            if p.name == "SHA256SUMS":
                checksums = compared
            if p.name == "source-manifest.json":
                source_manifest = compared
            if p.name == "aethron-0.2.0-source.tar.gz":
                source_archive = compared
            if p.name == "aethron.pyz":
                zipapp = compared
            if p.name == "sbom.cdx.json":
                sbom = compared
            artifact_manifest[p.name] = hashlib.sha256(compared).hexdigest()
        provenance = validate_provenance(
            provenance, revision, artifact_manifest["source-manifest.json"]
        )
        validate_checksums(checksums, artifact_manifest)
        manifest = validate_source_archive(source_archive, source_manifest)
        validate_source_manifest(clone, revision, manifest)
        validate_provenance_sources(provenance, manifest)
        validate_zipapp(zipapp, manifest)
        validate_sbom(sbom)
        call(
            [
                sys.executable,
                "-I",
                str(a / "aethron.pyz"),
                "evaluate",
                str(clone / "examples/person-blackout.json"),
            ],
            root,
            stdout=subprocess.DEVNULL,
            env=env,
        )
        for directory in (a, b):
            validate_artifacts(directory, artifact_manifest)
        validate_source(clone, revision)
        # zipimport consumer from outside the checkout, no PYTHONPATH dependency.
        code = 'import sys;sys.path.insert(0,sys.argv[1]);from aethron import evaluate;from pathlib import Path;r=evaluate(Path(sys.argv[2]).read_bytes());assert r["recommendation"]["action"]=="STOP"'
        call(
            [
                sys.executable,
                "-I",
                "-c",
                code,
                str(a / "aethron.pyz"),
                str(clone / "examples/person-blackout.json"),
            ],
            root,
            env=env,
        )
        for directory in (a, b):
            validate_artifacts(directory, artifact_manifest)
        validate_source(clone, revision)
        result = {
            "source_revision": revision,
            "clean_clone": True,
            "evaluation_gate_passed": evaluation.returncode == 0,
            "quickstart": evaluation.returncode == 0,
            "isolated_zipapp_consumer": True,
            "byte_identical_builds": True,
            "artifact_sha256": artifact_manifest,
        }
        print(json.dumps(result, sort_keys=True))
        if evaluation.returncode != 0:
            raise SystemExit("evaluation gate failed; independent packaging checks completed")


if __name__ == "__main__":
    run()
