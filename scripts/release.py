"""Deterministic source and executable artifacts, SBOM and unsigned local provenance."""

import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

if __package__:
    from .git_context import GIT_COMMAND_TIMEOUT_SECONDS, require_default_git_context
else:
    from git_context import GIT_COMMAND_TIMEOUT_SECONDS, require_default_git_context

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DEVICE_NAMES = frozenset(
    ("CON", "PRN", "AUX", "NUL")
    + tuple(prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³")
)


def _source_name(raw):
    """Match archive admission before host paths can normalize source names."""
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("release_source_path_invalid") from None
    # Source archives must not install Git administration files on extraction.
    # Check every component, including case variants on insensitive hosts;
    # ordinary source controls such as .gitignore remain valid.
    if any(part.casefold() == ".git" for part in name.split("/")):
        raise ValueError("release_source_path_invalid")
    # Match wheel admission for drive/stream syntax on every host. A drive
    # component can reset Path joining during the checkout walk on Windows;
    # a colon can also address an alternate stream instead of an ordinary file.
    # Match wheel admission for reserved punctuation and ASCII controls too,
    # including directory components, before certifying portable artifacts.
    if any(part in ("", ".", "..") for part in name.split("/")) or any(
        ord(character) < 32 or character in '<>:"\\|?*' for character in name
    ):
        raise ValueError("release_source_path_invalid")
    # Match wheel admission for names that Windows can normalize to a
    # different destination. Check directories too, without trimming names
    # and silently changing the committed source inventory.
    if any(part.endswith((".", " ")) for part in name.split("/")):
        raise ValueError("release_source_path_invalid")
    # Apply the wheel validator's device-name rule to source archives too.
    # Windows reserves these in every directory, including with extensions;
    # reject before checkout access can resolve a name to a device.
    if any(part.split(".", 1)[0].upper() in WINDOWS_DEVICE_NAMES for part in name.split("/")):
        raise ValueError("release_source_path_invalid")
    return name


def _reject_source_case_aliases(names):
    """Keep one spelling per folded path, including implicit directories."""
    spellings = {}
    for name in names:
        parts = name.split("/")
        for end in range(1, len(parts) + 1):
            prefix = "/".join(parts[:end])
            folded = prefix.casefold()
            if spellings.setdefault(folded, prefix) != prefix:
                raise ValueError("release_source_path_alias")


def committed_blobs(revision, *, root=None):
    """Read one immutable Git tree, never the mutable checkout behind provenance."""
    require_default_git_context(os.environ)
    root = ROOT if root is None else root
    tree = subprocess.check_output(
        ["git", "--no-replace-objects", "ls-tree", "-r", "-t", "-z", "--full-tree", revision],
        cwd=root,
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
    )
    entries = []
    trees = set()
    paths = set()
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        name = _source_name(name)
        # Match public-tree admission before reducing the inventory to blobs.
        # Including directories exposes duplicate subtrees and file/directory
        # collisions even when their descendant file paths are all distinct.
        if name in paths:
            raise ValueError("release_duplicate_tree_path")
        paths.add(name)
        if (mode, kind) == (b"040000", b"tree"):
            trees.add(oid)
            continue
        if mode not in (b"100644", b"100755") or kind != b"blob":
            raise ValueError("release_requires_regular_blobs")
        entries.append((name, oid))
    # Reuse wheel admission's case folding without rewriting source names.
    # Include empty directories and differently spelled parent components;
    # full-file-path comparisons alone miss directories with distinct children.
    _reject_source_case_aliases(paths)
    entries.sort()
    # Recursive ls-tree validates its starting object, but may traverse corrupt
    # nested trees without checking their hashes. Verify those raw objects too;
    # valid blob hashes alone cannot bind paths/modes to the named revision.
    # Shared and empty subtrees are included, with each tree read only once.
    objects = [(name, oid, b"blob") for name, oid in entries]
    objects.extend((None, oid, b"tree") for oid in sorted(trees))
    payload = io.BytesIO(
        subprocess.check_output(
            ["git", "--no-replace-objects", "cat-file", "--batch"],
            cwd=root,
            input=b"".join(oid + b"\n" for _, oid, _ in objects),
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    )
    blobs = {}
    for name, oid, kind in objects:
        error = "release_" + kind.decode("ascii")
        header = payload.readline().split()
        if len(header) != 3 or header[:2] != [oid, kind] or not header[2].isdigit():
            raise ValueError(error + "_response_invalid")
        size = int(header[2])
        data = payload.read(size)
        if len(data) != size or payload.read(1) != b"\n":
            raise ValueError(error + "_response_invalid")
        # cat-file can return a corrupt loose object's bytes under its requested
        # ID. Bind the actual payload to the tree entry before either a release
        # or its manifest verifier can certify it. SHA-1 here is the legacy Git
        # object format, not a choice of signature or security algorithm.
        if len(oid) == 40:
            digest = hashlib.sha1(usedforsecurity=False)
        elif len(oid) == 64:
            digest = hashlib.sha256()
        else:
            raise ValueError(error + "_response_invalid")
        digest.update(kind + b" " + str(size).encode("ascii") + b"\0")
        digest.update(data)
        if digest.hexdigest().encode("ascii") != oid:
            raise ValueError(error + "_hash_mismatch")
        if kind == b"blob":
            blobs[name] = data
    if payload.read(1):
        raise ValueError("release_blob_response_invalid")
    return blobs


def build(destination):
    require_default_git_context(os.environ)
    # Local refs/replace must not redefine the revision named by provenance.
    names = subprocess.check_output(
        ["git", "--no-replace-objects", "ls-files", "-z"],
        cwd=ROOT,
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
    )
    names = sorted(_source_name(n) for n in names.split(b"\0") if n)
    _reject_source_case_aliases(names)
    revision = subprocess.check_output(
        ["git", "--no-replace-objects", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
    ).strip()
    dirty = subprocess.check_output(
        ["git", "--no-replace-objects", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
    )
    if dirty:
        raise SystemExit("release requires clean committed source")
    try:
        # Preserve checkout admission; payload bytes come only from the pinned Git tree.
        for name in names:
            path = ROOT
            parts = Path(name).parts
            for index, part in enumerate(parts):
                path = path / part
                info = path.lstat()
                mode = info.st_mode
                valid = stat.S_ISREG(mode) if index == len(parts) - 1 else stat.S_ISDIR(mode)
                # Match verifier/package admission: Windows junctions can have
                # ordinary directory mode bits. Reject reparse attributes too,
                # before inspecting descendants or creating release artifacts.
                # Stable-tree admission only, not concurrent-replacement safety.
                redirected = getattr(info, "st_file_attributes", 0) & getattr(
                    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
                )
                if not valid or redirected:
                    raise SystemExit("release requires regular source files without symlinks")
        blobs = committed_blobs(revision)
    except OSError:
        raise SystemExit("release source unavailable") from None
    manifest = {n: hashlib.sha256(data).hexdigest() for n, data in blobs.items()}
    # Git admits names (including UTF-8 names) that USTAR cannot represent.
    # Validate the exact headers before reserving the output directory, so a
    # rejected source can be corrected and rebuilt at the same destination.
    members = []
    for name, data in blobs.items():
        info = tarfile.TarInfo("aethron-0.2.0/" + name)
        info.size = len(data)
        info.mode = 0o644
        info.mtime = 0
        info.tobuf(tarfile.USTAR_FORMAT, encoding="utf-8", errors="strict")
        members.append((name, info))
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=False)
    buffer = io.BytesIO()
    # Git names are admitted as UTF-8; host filesystem encodings must not
    # change their archive bytes or their USTAR representability.
    with tarfile.open(
        fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT, encoding="utf-8", errors="strict"
    ) as archive:
        for name, info in members:
            archive.addfile(info, io.BytesIO(blobs[name]))
    # GzipFile keeps the OS header stable on Python 3.11/3.12 too; pin all defaults
    # that affect bytes, including the compression level changed in Python 3.15.
    compressed = io.BytesIO()
    with gzip.GzipFile(
        filename="", mode="wb", compresslevel=9, fileobj=compressed, mtime=0
    ) as stream:
        stream.write(buffer.getvalue())
    (out / "aethron-0.2.0-source.tar.gz").write_bytes(compressed.getvalue())
    with zipfile.ZipFile(out / "aethron.pyz", "w", compression=zipfile.ZIP_STORED) as archive:
        app = {n: data for n, data in blobs.items() if n.startswith("aethron/")}
        app["__main__.py"] = b"from aethron.__main__ import main\nraise SystemExit(main())\n"
        app["LICENSE"] = blobs["LICENSE"]
        app["NOTICE"] = blobs["NOTICE"]
        for name, data in sorted(app.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            # The normalized Unix permission field needs the same creator on every host.
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    # Encode explicitly so host text newline translation cannot change artifact hashes.
    (out / "source-manifest.json").write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "aethron",
                "version": "0.2.0",
                "licenses": [{"license": {"id": "GPL-3.0-only"}}],
            }
        },
        "components": [
            {
                "type": "data",
                "name": "Amazon AOT derived25-frame evaluation excerpt",
                "version": "2026-10-08",
                "licenses": [{"license": {"id": "CDLA-Permissive-1.0"}}],
            },
            {
                "type": "data",
                "name": "NASA public-domain and CC0 RGB smoke photographs",
                "version": "scikit-image-v0.25.2",
                "licenses": [
                    {"license": {"name": "Public domain / CC0-1.0; see data/rgb-smoke/README.md"}}
                ],
            },
            {
                "type": "library",
                "name": "Python standard library",
                "version": "runtime-provided",
                "licenses": [{"license": {"id": "Python-2.0"}}],
            },
        ],
        "dependencies": [],
        "properties": [
            {
                "name": "aethron:optional-vision",
                "value": "numpy2.3.5;opencv-python-headless4.13.0.92; separately installed, not in zipapp",
            },
            {
                "name": "aethron:optional-coreml",
                "value": "onnxruntime1.30.0;flatbuffers25.12.19;protobuf7.36.2; separate macOS Apple Silicon opt-in, not bundled",
            },
            {
                "name": "aethron:optional-model-sha256",
                "value": "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063",
            },
        ],
    }
    (out / "sbom.cdx.json").write_bytes(
        (json.dumps(sbom, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    provenance = {
        "source_revision": revision,
        "source_manifest_sha256": hashlib.sha256(
            (out / "source-manifest.json").read_bytes()
        ).hexdigest(),
        "builder": "scripts/release.py",
        "evidence": "local unsigned candidate; not hosted attestation",
        "runtime_dependencies": "Python 3.9+ standard library",
        "model_sha256": manifest["aethron/models/rules.json"],
        "data_manifests": {n: h for n, h in manifest.items() if n.endswith("freeze.json")},
    }
    (out / "provenance.json").write_bytes(
        (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    checksums = "".join(
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
        for p in sorted(out.iterdir())
        if p.is_file() and p.name != "SHA256SUMS"
    )
    (out / "SHA256SUMS").write_bytes(checksums.encode("utf-8"))
    return revision


if __name__ == "__main__":
    import sys

    print(build(sys.argv[1] if len(sys.argv) > 1 else "dist"))
