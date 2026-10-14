"""Synthetic reporting fixtures and real Python startup probes; no product build."""

import contextlib
import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import reproduce

ZIP_MAIN = b"from aethron.__main__ import main\nraise SystemExit(main())\n"
PROVENANCE_DECLARATIONS = {
    "builder": "scripts/release.py",
    "evidence": "local unsigned candidate; not hosted attestation",
    "runtime_dependencies": "Python 3.9+ standard library",
}
SBOM = {
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
    "components": [],
    "dependencies": [],
    "properties": [],
}
SBOM_BYTES = json.dumps(SBOM).encode()
SOURCE_FILES = {
    "source.txt": b"synthetic source\x00\xff\n",
    "empty.txt": b"",
    "LICENSE": b"synthetic license\n",
    "NOTICE": b"synthetic notice\n",
    "aethron/__init__.py": (
        b"import importlib.util\n"
        b"assert importlib.util.find_spec('zip_shadow') is None\n"
        b"def evaluate(data):\n    return {'recommendation': {'action': 'STOP'}}\n"
    ),
    "aethron/__main__.py": b"def main():\n    return 0\n",
    "aethron/data.bin": b"\x00\xff",
    "aethron/empty.txt": b"",
    "aethron/models/rules.json": b'{"fixture": "rules"}\n',
    "data/first/freeze.json": b'{"fixture": "first"}\n',
    "data/second/freeze.json": b'{"fixture": "second"}\n',
}
SOURCE_MANIFEST = json.dumps(
    {name: hashlib.sha256(data).hexdigest() for name, data in SOURCE_FILES.items()}
).encode()


def provenance_sources(files):
    return {
        "model_sha256": hashlib.sha256(files["aethron/models/rules.json"]).hexdigest(),
        "data_manifests": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in files.items()
            if name.endswith("freeze.json")
        },
    }


def executable_archive(
    defect=None, *, files=None, metadata=None, local_header=None, end_record=None
):
    files = SOURCE_FILES if files is None else files
    entries = [("__main__.py", ZIP_MAIN)] + [
        (name, data)
        for name, data in files.items()
        if name.startswith("aethron/") or name in ("LICENSE", "NOTICE")
    ]
    if defect == "missing":
        entries.pop()
    elif defect == "extra":
        entries.append(("extra.txt", b"unexpected"))
    elif defect == "duplicate":
        entries.append(entries[-1])
    elif defect == "empty":
        entries = []
    buffer = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(buffer, "w") as archive:
        warnings.simplefilter("ignore", UserWarning)
        for name, data in entries:
            if defect == "launcher" and name == "__main__.py":
                data = b"raise SystemExit(0)\n"
            if name == "aethron/data.bin":
                if defect == "content":
                    data = b"wrong bytes"
                elif defect == "traversal":
                    name = "aethron/../data.bin"
                elif defect == "directory":
                    name += "/"
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o644 << 16
            if name == "aethron/data.bin":
                for key, value in (metadata or {}).items():
                    setattr(info, key, value)
                if defect in ("local-extra", "both-extra"):
                    info.extra = b"\xfe\xca\x04\x00data"
                if defect == "member-comment":
                    info.comment = b"unverified comment\x00\xff"
            if defect == "symlink" and name == "aethron/data.bin":
                info.external_attr = (stat.S_IFLNK | 0o644) << 16
            elif defect == "special" and name == "aethron/data.bin":
                info.external_attr = (stat.S_IFIFO | 0o644) << 16
            elif defect == "compressed" and name == "aethron/data.bin":
                info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
            if name == "aethron/data.bin":
                # The local header is already written; vary the directory's
                # extension independently to cover both parsing boundaries.
                if defect == "local-extra":
                    info.extra = b""
                elif defect == "central-extra":
                    info.extra = b"\xfe\xca\x04\x00data"
            if (
                (name == "__main__.py" and defect in ("unlisted-middle", "gap-middle"))
                or (name == entries[-1][0] and defect in ("unlisted-tail", "gap-tail"))
                or (name == "aethron/data.bin" and defect == "gap-in-compressed-size")
            ):
                if defect.startswith("unlisted"):
                    # Keep a real local record, but omit its central-directory entry.
                    archive.writestr("unlisted.txt", b"unverified local payload")
                    archive.filelist.pop()
                    del archive.NameToInfo["unlisted.txt"]
                else:
                    gap = b"\x00unverified gap\x00"
                    buffer.write(gap)
                    archive.start_dir = buffer.tell()
                    if defect == "gap-in-compressed-size":
                        archive.filelist[-1].compress_size += len(gap)
        if defect == "reordered-directory":
            archive.filelist.reverse()
    payload = buffer.getvalue()
    if end_record is not None:
        # Alter the directory summary without changing any member or directory entry.
        offset, width, value = end_record
        start = len(payload) - 22 + offset
        payload = payload[:start] + value.to_bytes(width, "little") + payload[start + width :]
    if local_header is not None:
        # Mutate only a local record, leaving central metadata and file bytes intact.
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            start = archive.getinfo("aethron/data.bin").header_offset
        offset, width, value = local_header
        start += offset
        payload = payload[:start] + value.to_bytes(width, "little") + payload[start + width :]
    if defect == "prefix-script":
        return b"#!/bin/sh\nexit 0\n" + payload
    if defect == "prefix-zero":
        return b"\x00" + payload
    if defect == "prefix-archive":
        prefix = io.BytesIO()
        with zipfile.ZipFile(prefix, "w") as archive:
            archive.writestr("unlisted.txt", b"unverified prefix")
        return prefix.getvalue() + payload
    if defect == "suffix-bytes":
        return payload + b"unverified suffix"
    if defect == "suffix-zero":
        return payload + b"\x00"
    if defect == "suffix-end-record":
        return payload + payload[-22:]
    if defect == "archive-comment":
        return payload[:-2] + b"\x07\x00" + b"comment"
    if defect == "crc":
        payload = payload.replace(b"synthetic notice\n", b"different notice\n")
    if defect == "truncated":
        return payload[:60]
    return b"not ZIP" if defect == "malformed" else payload


def source_archive(defect=None, *, files=None, metadata=None):
    """Real compressed TAR bytes, with optional independently checksummed defects."""
    files = SOURCE_FILES if files is None else files
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        entries = list(files.items())
        if defect == "missing":
            entries.pop()
        elif defect == "extra":
            entries.append(("extra.txt", b"extra"))
        elif defect == "duplicate":
            entries.append(entries[0])
        elif defect == "empty":
            entries = []
        for name, data in entries:
            member = tarfile.TarInfo("aethron-0.2.0/" + name)
            if name == "source.txt":
                for key, value in (metadata or {}).items():
                    setattr(member, key, value)
                if defect == "content":
                    data = b"wrong source bytes"
                elif defect == "prefix":
                    member.name = "other-project/" + name
                elif defect == "traversal":
                    member.name = "aethron-0.2.0/../" + name
                elif defect in ("symlink", "hardlink", "directory", "fifo"):
                    member.type = {
                        "symlink": tarfile.SYMTYPE,
                        "hardlink": tarfile.LNKTYPE,
                        "directory": tarfile.DIRTYPE,
                        "fifo": tarfile.FIFOTYPE,
                    }[defect]
                    member.linkname = "aethron-0.2.0/empty.txt"
                    data = b""
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    raw = buffer.getvalue()
    if defect == "truncated":
        raw = raw[:520]
    if defect in ("tar-trailing-file", "gzip-trailing-file", "tar-trailing-duplicate"):
        tail = io.BytesIO()
        with tarfile.open(fileobj=tail, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            name = "source.txt" if defect == "tar-trailing-duplicate" else "unlisted.txt"
            member = tarfile.TarInfo("aethron-0.2.0/" + name)
            data = b"unverified trailing source\n"
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if defect == "gzip-trailing-file":
            return gzip.compress(raw, mtime=0) + gzip.compress(tail.getvalue(), mtime=0)
        raw += tail.getvalue()
    elif defect == "tar-trailing-bytes":
        raw += b"unverified trailing bytes"
    elif defect == "tar-distant-trailing-byte":
        raw += b"\x00" * (2 * 1024 * 1024) + b"x"
    compressed = gzip.compress(raw, mtime=0)
    if defect == "gzip-footer":
        return compressed[:-8]
    if defect == "gzip-crc":
        return compressed[:-8] + bytes([compressed[-8] ^ 1]) + compressed[-7:]
    if defect == "gzip-size":
        return compressed[:-4] + bytes([compressed[-4] ^ 1]) + compressed[-3:]
    if defect == "gzip-trailing-header":
        return compressed + b"\x1f\x8b"
    if defect == "gzip-trailing-deflate":
        # Valid second gzip header followed by the reserved DEFLATE block type.
        return compressed + b"\x1f\x8b\x08" + b"\x00" * 7 + b"\x07"
    return b"not gzip" if defect == "malformed" else compressed


class ReproductionReport(unittest.TestCase):
    def test_replacement_refs_cannot_hide_changed_source(self):
        for kind in ("commit", "tree"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                clone = Path(directory)

                def git(*args, clone=clone):
                    return subprocess.check_output(
                        [
                            "git",
                            "-c",
                            "user.name=Reproduction Fixture",
                            "-c",
                            "user.email=fixture@example.invalid",
                            "-c",
                            "commit.gpgsign=false",
                            "-c",
                            "core.hooksPath=" + str(clone / "no-hooks"),
                            *args,
                        ],
                        cwd=clone,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                    ).strip()

                git("init", "--quiet")
                # Exercise the Windows checkout default on every test host.
                git("config", "core.autocrlf", "true")
                # This fixture compares immutable bytes, not normalized text.
                (clone / ".gitattributes").write_bytes(b"source.txt -text\n")
                source = clone / "source.txt"
                source.write_bytes(b"original source\n")
                git("add", "source.txt", ".gitattributes")
                git("commit", "--quiet", "-m", "original source")
                revision = git("rev-parse", "HEAD")
                original = git("rev-parse", "HEAD^{tree}") if kind == "tree" else revision
                source.write_bytes(b"replacement source\n")
                git("add", "source.txt")
                git("commit", "--quiet", "-m", "replacement source")
                replacement = git("rev-parse", "HEAD^{tree}" if kind == "tree" else "HEAD")
                git("reset", "--hard", revision)
                git("replace", original, replacement)

                # Merely having a replacement ref must not reject original source.
                with self.subTest(source="original"):
                    reproduce.validate_source(clone, revision)
                git("read-tree", "--reset", "-u", "HEAD")
                self.assertEqual(source.read_bytes(), b"replacement source\n")
                self.assertEqual(git("rev-parse", "HEAD"), revision)
                self.assertEqual(git("status", "--porcelain"), "")
                with self.assertRaisesRegex(ValueError, "^reproduction_source_changed$"):
                    reproduce.validate_source(clone, revision)

    def test_source_validation_with_real_git_changes(self):
        for mutation in (
            None,
            "ignored",
            "modified",
            "deleted",
            "staged",
            "untracked",
            "revision",
            "assume-unchanged",
            "skip-worktree",
            "both-flags",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                clone = Path(directory)

                def git(*args, clone=clone):
                    return subprocess.check_output(
                        [
                            "git",
                            "-c",
                            "user.name=Reproduction Fixture",
                            "-c",
                            "user.email=fixture@example.invalid",
                            "-c",
                            "commit.gpgsign=false",
                            "-c",
                            "core.hooksPath=" + str(clone / "no-hooks"),
                            *args,
                        ],
                        cwd=clone,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                    ).strip()

                git("init", "--quiet")
                source = clone / "source.txt"
                source.write_bytes(b"original source\n")
                (clone / ".gitignore").write_bytes(b"build/\n")
                git("add", "source.txt", ".gitignore")
                git("commit", "--quiet", "-m", "synthetic source")
                revision = git("rev-parse", "HEAD")
                if mutation in ("modified", "staged"):
                    source.write_bytes(b"changed source\n")
                    if mutation == "staged":
                        git("add", "source.txt")
                elif mutation == "deleted":
                    source.unlink()
                elif mutation == "untracked":
                    (clone / "extra.txt").write_bytes(b"extra source\n")
                    # The checker must override a user preference hiding untracked files.
                    git("config", "status.showUntrackedFiles", "no")
                elif mutation == "revision":
                    # Even a clean new commit with identical source cannot relabel evidence.
                    git("commit", "--quiet", "--allow-empty", "-m", "different revision")
                elif mutation == "ignored":
                    (clone / "build").mkdir()
                    (clone / "build" / "output.txt").write_bytes(b"ignored output\n")
                elif mutation in ("assume-unchanged", "skip-worktree", "both-flags"):
                    flags = (
                        ("assume-unchanged", "skip-worktree")
                        if mutation == "both-flags"
                        else (mutation,)
                    )
                    for flag in flags:
                        git("update-index", "--" + flag, "source.txt")
                    source.write_bytes(b"hidden changed source\n")
                    self.assertEqual(git("status", "--porcelain"), "")
                if mutation in (None, "ignored"):
                    reproduce.validate_source(clone, revision)
                else:
                    original_index = (clone / ".git" / "index").read_bytes()
                    with self.assertRaisesRegex(ValueError, "^reproduction_source_changed$"):
                        reproduce.validate_source(clone, revision)
                    if mutation in ("assume-unchanged", "skip-worktree", "both-flags"):
                        self.assertEqual((clone / ".git" / "index").read_bytes(), original_index)
                        self.assertEqual(source.read_bytes(), b"hidden changed source\n")

    def test_optimized_execution_is_rejected_before_cloning(self):
        for flag in ("-O", "-OO"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(
                    [sys.executable, "-I", flag, str(Path(reproduce.__file__).resolve())],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.strip(), "reproduce_requires_assertions")
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_checked_call_preserves_arguments_and_rejects_failed_child(self):
        # Removing check=True or introducing shell interpretation must fail this test.
        argument = 'space ; $name "quoted" * & |'
        code = "import sys; print(repr(sys.argv[1])); sys.exit(int(sys.argv[2]))"
        with tempfile.TemporaryDirectory(prefix="report-call-") as directory:
            for status in (0, 7):
                with self.subTest(status=status):
                    args = [sys.executable, "-I", "-S", "-c", code, argument, str(status)]
                    if status:
                        with self.assertRaises(subprocess.CalledProcessError) as caught:
                            reproduce.call(args, directory, capture_output=True, timeout=5)
                        result = caught.exception
                    else:
                        result = reproduce.call(args, directory, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, status)
                    self.assertEqual(result.stdout.decode().strip(), repr(argument))
                    self.assertEqual(result.stderr, b"")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def invoke(
        self,
        *,
        evaluation=0,
        mismatch=None,
        refusal=1,
        consumer=0,
        mutation=None,
        mutate_at=1,
        mutate_lane="a",
        real_consumers=False,
        source_mutation=None,
        source_mutate_at="consumer2",
        verification_error=None,
        check_workspace=False,
        guard_artifact_reads=False,
        inventory_defect=None,
        inventory_lanes=("a", "b"),
        provenance_bytes=None,
        sbom_bytes=SBOM_BYTES,
        checksum_defect=None,
        manifest_bytes=None,
        artifact_files=None,
        archive_defect=None,
        archive_metadata=None,
        zip_defect=None,
        zip_metadata=None,
        zip_local_header=None,
        zip_end_record=None,
        python_probes=None,
    ):
        output = io.StringIO()
        diagnostics = io.StringIO()
        consumers = []
        workspaces = []
        artifact_files = SOURCE_FILES if artifact_files is None else artifact_files
        if manifest_bytes is None:
            manifest_bytes = json.dumps(
                {name: hashlib.sha256(data).hexdigest() for name, data in artifact_files.items()}
            ).encode()
        payload = executable_archive(
            zip_defect,
            files=artifact_files,
            metadata=zip_metadata,
            local_header=zip_local_header,
            end_record=zip_end_record,
        )
        revision = "a" * 40
        clone_revision = revision
        source_status = b""
        index_entries = b"H examples/person-blackout.json\0"
        real_process = subprocess.run
        real_read = Path.read_bytes

        def checked_read(path):
            if inventory_defect is not None and path.parent.name in ("a", "b"):
                self.fail("artifact read before incomplete inventory rejection")
            if guard_artifact_reads and path.parent.name in ("a", "b"):
                self.assertFalse(path.parent.is_symlink(), "read through linked directory")
                self.assertFalse(path.is_symlink(), "read linked artifact")
                self.assertTrue(path.is_file(), "read non-regular artifact")
            return real_read(path)

        def mutate_artifact(root):
            artifact = root / mutate_lane / "aethron.pyz"
            if mutation == "changed":
                artifact.write_bytes(b"changed after comparison")
            elif mutation == "removed":
                artifact.unlink()
            elif mutation == "extra":
                artifact.with_name("uncompared.zip").write_bytes(b"extra artifact")
            elif mutation == "file_link":
                target = artifact.parent.parent / "external.pyz"
                artifact.replace(target)
                artifact.symlink_to(target)
            elif mutation == "directory_link":
                directory = artifact.parent
                target = directory.with_name("external-build")
                directory.replace(target)
                directory.symlink_to(target, target_is_directory=True)
            elif mutation == "directory_entry":
                artifact.unlink()
                artifact.mkdir()
            elif mutation == "fifo":
                artifact.unlink()
                os.mkfifo(artifact)

        def fake_process(args, **kwargs):
            nonlocal clone_revision, source_status, index_entries
            if python_probes is not None and args[0] == sys.executable:
                # Exercise real interpreter startup with the stage's environment.
                # Build/evaluation bodies below remain synthetic fixtures.
                isolated = ["-I"] if args[1:2] == ["-I"] else []
                real_process(
                    [
                        sys.executable,
                        *isolated,
                        "-c",
                        "import importlib.util, os; "
                        "assert 'PYTHONHOME' not in os.environ; "
                        "assert 'PYTHONPATH' not in os.environ; "
                        "assert importlib.util.find_spec('caller_shadow') is None; "
                        "assert os.environ['AETHRON_REPRODUCTION_TEST'] == 'preserved'",
                    ],
                    cwd=kwargs["cwd"],
                    env=kwargs.get("env"),
                    capture_output=True,
                    check=True,
                    timeout=5,
                )
                python_probes.append(args[1:])
            stage = None
            if args[1:2] == ["scripts/verify.py"]:
                stage = "verify"
            elif args[1:2] == ["scripts/release.py"] and Path(args[-1]).name == "b":
                stage = "build"
            elif args[1:2] == ["-I"]:
                stage = "consumer" + str(len(consumers) + 1)
            if source_mutation and stage == source_mutate_at:
                if source_mutation == "revision":
                    clone_revision = "b" * 40
                elif source_mutation in ("assume-unchanged", "skip-worktree", "both-flags"):
                    tag = {
                        "assume-unchanged": b"h",
                        "skip-worktree": b"S",
                        "both-flags": b"s",
                    }[source_mutation]
                    index_entries = tag + b" examples/person-blackout.json\0"
                else:
                    source_status = b" M changed-source.py\n"
            if args[:2] == ["git", "clone"]:
                workspaces.append(Path(args[-1]).parent)
                (Path(args[-1]) / "aethron").mkdir(parents=True)
                examples = Path(args[-1]) / "examples"
                examples.mkdir()
                (examples / "person-blackout.json").write_bytes(b"{}")
            elif args[1:2] == ["scripts/temporal_evaluate.py"]:
                evidence = Path(args[-1])
                evidence.mkdir()
                (evidence / "result.json").write_bytes(b'{"fixture": "evaluation evidence"}\n')
                return subprocess.CompletedProcess(args, evaluation)
            elif args[1:2] == ["scripts/release.py"]:
                destination = Path(args[-1])
                if destination.name == "refused":
                    return subprocess.CompletedProcess(
                        args, refusal, stderr=b"release requires clean committed source"
                    )
                destination.mkdir()
                changed = destination.name == "b"
                name = "unexpected.pyz" if changed and mismatch == "names" else "aethron.pyz"
                data = b"different bytes" if changed and mismatch == "bytes" else payload
                (destination / name).write_bytes(data)
                for sidecar in (
                    "aethron-0.2.0-source.tar.gz",
                    "source-manifest.json",
                    "sbom.cdx.json",
                    "provenance.json",
                    "SHA256SUMS",
                ):
                    (destination / sidecar).write_bytes(b"synthetic sidecar")
                (destination / "sbom.cdx.json").write_bytes(sbom_bytes)
                (destination / "source-manifest.json").write_bytes(manifest_bytes)
                (destination / "aethron-0.2.0-source.tar.gz").write_bytes(
                    source_archive(archive_defect, files=artifact_files, metadata=archive_metadata)
                )
                (destination / "provenance.json").write_bytes(
                    json.dumps(
                        {
                            **PROVENANCE_DECLARATIONS,
                            "source_revision": revision,
                            **provenance_sources(artifact_files),
                            "source_manifest_sha256": hashlib.sha256(
                                real_read(destination / "source-manifest.json")
                            ).hexdigest(),
                        }
                    ).encode()
                    if provenance_bytes is None
                    else provenance_bytes
                )
                checksums = b"".join(
                    hashlib.sha256(real_read(path)).hexdigest().encode()
                    + b"  "
                    + path.name.encode()
                    + b"\n"
                    for path in sorted(destination.iterdir())
                    if path.name != "SHA256SUMS"
                )
                lines = checksums.splitlines(keepends=True)
                if checksum_defect == "empty":
                    checksums = b""
                elif checksum_defect == "malformed":
                    checksums = b"not checksums\n"
                elif checksum_defect == "encoding":
                    checksums = b"\xff"
                elif checksum_defect == "missing":
                    checksums = b"".join(lines[1:])
                elif checksum_defect == "duplicate":
                    checksums += lines[0]
                elif checksum_defect == "wrong-digest":
                    checksums = b"0" * 64 + checksums[64:]
                elif checksum_defect == "extra":
                    checksums += b"0" * 64 + b"  extra.txt\n"
                elif checksum_defect == "self":
                    checksums += b"0" * 64 + b"  SHA256SUMS\n"
                elif checksum_defect == "path":
                    checksums = checksums.replace(b"  aethron.pyz", b"  ../aethron.pyz")
                elif checksum_defect == "nul":
                    checksums += b"\0"
                (destination / "SHA256SUMS").write_bytes(checksums)
                if inventory_defect is not None and destination.name in inventory_lanes:
                    if inventory_defect == "empty":
                        for path in destination.iterdir():
                            path.unlink()
                    elif inventory_defect == "extra":
                        (destination / "unexpected.txt").write_bytes(b"unexpected")
                    else:
                        (destination / inventory_defect).unlink()
                if destination.name == "b" and mutation is not None and mutate_at == 0:
                    mutate_artifact(destination.parent)
            elif args[1:2] == ["scripts/verify.py"] or args[1:3] == ["-m", "aethron"]:
                if args[1:2] == ["scripts/verify.py"] and verification_error is not None:
                    (workspaces[0] / "partial.bin").write_bytes(b"partial\x00evidence")
                    raise verification_error
            elif args[1:2] == ["-I"] or args[1].endswith("aethron.pyz"):
                consumers.append(args)
                if mutation is not None and len(consumers) == mutate_at:
                    mutate_artifact(Path(kwargs["cwd"]))
                if consumer:
                    if kwargs.get("check"):
                        raise subprocess.CalledProcessError(consumer, args)
                    return subprocess.CompletedProcess(args, consumer)
                if real_consumers:
                    return real_process(args, **kwargs)
            else:
                self.fail(f"Unexpected process request: {args}")
            return subprocess.CompletedProcess(args, 0)

        def git_output(args, **kwargs):
            objects = {
                name: hashlib.sha1(
                    b"blob " + str(len(data)).encode() + b"\0" + data, usedforsecurity=False
                ).hexdigest()
                for name, data in SOURCE_FILES.items()
            }
            if args == [
                "git",
                "--no-replace-objects",
                "ls-tree",
                "-r",
                "-z",
                "--full-tree",
                revision,
            ]:
                self.assertEqual(Path(kwargs["cwd"]), workspaces[0] / "source")
                return b"".join(
                    b"100644 blob " + objects[name].encode() + b"\t" + name.encode() + b"\0"
                    for name in sorted(SOURCE_FILES)
                )
            if args == ["git", "--no-replace-objects", "cat-file", "--batch"]:
                self.assertEqual(Path(kwargs["cwd"]), workspaces[0] / "source")
                by_oid = {objects[name].encode(): data for name, data in SOURCE_FILES.items()}
                return b"".join(
                    oid + b" blob " + str(len(by_oid[oid])).encode() + b"\n" + by_oid[oid] + b"\n"
                    for oid in kwargs["input"].splitlines()
                )
            if args == ["git", "--no-replace-objects", "ls-files", "-v", "-z"]:
                return index_entries
            if args == ["git", "--no-replace-objects", "rev-parse", "HEAD"]:
                return clone_revision + "\n"
            if args == [
                "git",
                "--no-replace-objects",
                "status",
                "--porcelain",
                "--untracked-files=normal",
            ]:
                return source_status
            self.fail(f"Unexpected Git request: {args}")

        error = None
        with (
            tempfile.TemporaryDirectory(prefix="reproduction-test-") as sandbox,
            patch.object(tempfile, "tempdir", sandbox),
            patch.object(reproduce.subprocess, "run", side_effect=fake_process),
            patch.object(reproduce.subprocess, "check_output", side_effect=git_output),
            patch.object(Path, "read_bytes", checked_read),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(diagnostics),
        ):
            try:
                reproduce.run()
            except (
                SystemExit,
                AssertionError,
                ValueError,
                subprocess.CalledProcessError,
                KeyboardInterrupt,
            ) as caught:
                error = caught
            if check_workspace:
                self.assertEqual(len(workspaces), 1)
                workspace = workspaces[0]
                if error is None:
                    self.assertFalse(workspace.exists())
                    self.assertEqual(diagnostics.getvalue(), "")
                else:
                    self.assertTrue(workspace.is_dir(), "failed run erased its evidence")
                    self.assertIn(str(workspace), diagnostics.getvalue())
                    self.assertEqual(
                        (workspace / "source/examples/person-blackout.json").read_bytes(), b"{}"
                    )
                    if verification_error is not None:
                        self.assertIs(error, verification_error)
                        self.assertEqual(
                            (workspace / "partial.bin").read_bytes(), b"partial\x00evidence"
                        )
                    else:
                        self.assertEqual(
                            (workspace / "evaluation/result.json").read_bytes(),
                            b'{"fixture": "evaluation evidence"}\n',
                        )
                        self.assertEqual((workspace / "a/aethron.pyz").read_bytes(), payload)
        return output.getvalue(), error, consumers, payload, revision

    def test_failed_runs_retain_evidence_and_original_failure(self):
        cases = (
            {"evaluation": 1},
            {"mismatch": "bytes"},
            {"consumer": 7},
            {"verification_error": subprocess.CalledProcessError(9, ["synthetic-check"])},
            {"verification_error": KeyboardInterrupt()},
        )
        for case in cases:
            with self.subTest(case=case):
                _, error, _, _, _ = self.invoke(check_workspace=True, **case)
                self.assertIsNotNone(error)

    def test_success_removes_temporary_workspace(self):
        _, error, _, _, _ = self.invoke(check_workspace=True, real_consumers=True)
        self.assertIsNone(error)

    def test_workspace_cleanup_handles_readonly_files_without_hiding_other_errors(self):
        unlink = os.unlink

        def check(case):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as area:
                denied = PermissionError("synthetic Windows read-only file")
                failure = OSError("synthetic I/O failure") if case == "other-error" else denied
                attempts = []

                def windows_unlink(path, *, dir_fd=None):
                    if Path(path).name == "pack.idx":
                        attempts.append(path)
                        if case != "readonly" or not target.stat().st_mode & stat.S_IWUSR:
                            raise failure
                    if dir_fd is None:
                        return unlink(path)
                    return unlink(path, dir_fd=dir_fd)

                def run():
                    nonlocal target
                    with reproduce.reproduction_workspace(dir=area) as workspace:
                        target = Path(workspace) / "pack.idx"
                        target.write_bytes(b"synthetic Git pack index")
                        target.chmod(0o600 if case == "writable-denied" else 0o400)
                    return Path(workspace)

                target = None
                with patch.object(os, "unlink", side_effect=windows_unlink):
                    if case == "readonly":
                        self.assertFalse(run().exists())
                        self.assertEqual(len(attempts), 2)
                    else:
                        with self.assertRaises(type(failure)) as raised:
                            run()
                        self.assertIs(raised.exception, failure)
                        self.assertEqual(target.read_bytes(), b"synthetic Git pack index")
                        self.assertEqual(len(attempts), 2 if case == "retry-denied" else 1)
                if target.exists():
                    target.chmod(0o600)

        for case in ("readonly", "writable-denied", "other-error", "retry-denied"):
            check(case)

    def test_workspace_lifetime_survives_real_process_exit(self):
        code = """
import importlib.util
import sys
import tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("reproduce", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
tempfile.tempdir = sys.argv[2]
with module.reproduction_workspace() as temporary:
    print(temporary, flush=True)
    Path(temporary, "partial.bin").write_bytes(b"retained evidence")
    if sys.argv[3] == "fail":
        raise SystemExit(7)
"""
        for outcome in ("pass", "fail"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as sandbox:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-c",
                        code,
                        str(Path(reproduce.__file__).resolve()),
                        sandbox,
                        outcome,
                    ],
                    cwd=sandbox,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(result.returncode, 7 if outcome == "fail" else 0)
                workspace = Path(result.stdout.strip())
                self.assertEqual(workspace.parent, Path(sandbox))
                if outcome == "fail":
                    self.assertEqual((workspace / "partial.bin").read_bytes(), b"retained evidence")
                    self.assertIn(str(workspace), result.stderr)
                else:
                    self.assertFalse(workspace.exists())
                    self.assertEqual(result.stderr, "")

    def test_source_changes_cannot_be_reported_as_clean_or_relabel_revision(self):
        for stage, consumed in (("verify", 0), ("build", 0), ("consumer1", 1), ("consumer2", 2)):
            for mutation in (
                "dirty",
                "revision",
                "assume-unchanged",
                "skip-worktree",
                "both-flags",
            ):
                with self.subTest(stage=stage, mutation=mutation):
                    output, error, consumers, _, _ = self.invoke(
                        source_mutation=mutation, source_mutate_at=stage
                    )
                    self.assertIsInstance(error, ValueError)
                    self.assertEqual(str(error), "reproduction_source_changed")
                    self.assertEqual(output, "")
                    self.assertEqual(len(consumers), consumed)

    def test_success_reports_compared_bytes_and_clone_revision(self):
        output, error, consumers, payload, revision = self.invoke()
        self.assertIsNone(error)
        self.assertEqual(len(consumers), 2)
        report = json.loads(output)
        self.assertEqual(report["source_revision"], revision)
        expected = {
            "aethron.pyz": hashlib.sha256(payload).hexdigest(),
            "provenance.json": hashlib.sha256(
                json.dumps(
                    {
                        **PROVENANCE_DECLARATIONS,
                        "source_revision": revision,
                        **provenance_sources(SOURCE_FILES),
                        "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST).hexdigest(),
                    }
                ).encode()
            ).hexdigest(),
            "aethron-0.2.0-source.tar.gz": hashlib.sha256(source_archive()).hexdigest(),
            "source-manifest.json": hashlib.sha256(SOURCE_MANIFEST).hexdigest(),
            "sbom.cdx.json": hashlib.sha256(SBOM_BYTES).hexdigest(),
        }
        checksums = "".join(f"{expected[name]}  {name}\n" for name in sorted(expected)).encode()
        expected["SHA256SUMS"] = hashlib.sha256(checksums).hexdigest()
        self.assertEqual(report["artifact_sha256"], expected)
        for field in (
            "clean_clone",
            "evaluation_gate_passed",
            "quickstart",
            "isolated_zipapp_consumer",
            "byte_identical_builds",
        ):
            self.assertIs(report[field], True)

    def test_identical_invalid_sbom_rejects_before_consumers(self):
        cases = [b"synthetic sidecar", b"\xff", b"[]", b"null", b"{}"]
        for path, values in (
            (("bomFormat",), (None, "SPDX", 1)),
            (("specVersion",), (None, "1.5", 1.6)),
            (("version",), (None, 0, True, 1.0, "1", 2)),
            (("metadata",), (None, [], "metadata")),
            (("metadata", "component"), (None, [], "component")),
            (("metadata", "component", "type"), (None, "library")),
            (("metadata", "component", "name"), (None, "other")),
            (("metadata", "component", "version"), (None, "0.1.0")),
            (("metadata", "component", "licenses"), (None, [], [{"license": {"id": "MIT"}}])),
        ):
            for value in values:
                bom = json.loads(SBOM_BYTES)
                parent = bom
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
                cases.append(json.dumps(bom).encode())
            del parent[path[-1]]
            cases.append(json.dumps(bom).encode())
        cases.extend(
            (
                SBOM_BYTES.replace(b'"version": 1,', b'"version": 0, "version": 1,', 1),
                SBOM_BYTES.replace(b'"name": "aethron"', b'"name": "other", "name": "aethron"'),
                SBOM_BYTES[:-1] + b', "extra": NaN}',
                SBOM_BYTES[:-1] + b', "extra": Infinity}',
            )
        )
        for index, payload in enumerate(cases):
            with self.subTest(case=index, payload=payload):
                output, error, consumers, _, _ = self.invoke(
                    sbom_bytes=payload, real_consumers=True, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_sbom_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_sbom_formatting_and_additional_metadata_preserve_acceptance(self):
        bom = json.loads(SBOM_BYTES)
        bom["metadata"]["component"]["description"] = "Synthetic release fixture"
        payload = json.dumps(bom, indent=2, sort_keys=True).encode()
        output, error, consumers, _, _ = self.invoke(sbom_bytes=payload, real_consumers=True)
        self.assertIsNone(error)
        self.assertEqual(len(consumers), 2)
        self.assertEqual(
            json.loads(output)["artifact_sha256"]["sbom.cdx.json"],
            hashlib.sha256(payload).hexdigest(),
        )

    def test_identical_invalid_checksums_reject_before_consumers(self):
        for defect in (
            "empty",
            "malformed",
            "encoding",
            "missing",
            "duplicate",
            "wrong-digest",
            "extra",
            "self",
            "path",
            "nul",
        ):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    checksum_defect=defect, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_checksums_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_identical_source_archive_defects_reject_before_consumers(self):
        for defect in (
            "content",
            "missing",
            "extra",
            "duplicate",
            "empty",
            "prefix",
            "traversal",
            "symlink",
            "hardlink",
            "directory",
            "fifo",
            "truncated",
            "malformed",
        ):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    archive_defect=defect, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_source_archive_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_source_archive_metadata_rejects_before_consumers(self):
        for field, value in (
            ("mode", 0o4755),
            ("mode", 0o2755),
            ("mode", 0o666),
            ("mode", 0o755),
            ("uid", 1234),
            ("gid", 1234),
            ("uname", "unverified-owner"),
            ("gname", "unverified-group"),
            ("mtime", 1234),
        ):
            with self.subTest(field=field, value=value):
                output, error, consumers, _, _ = self.invoke(
                    archive_metadata={field: value}, check_workspace=True, real_consumers=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_source_archive_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_gzip_integrity_defects_reject_before_consumers(self):
        for defect in (
            "gzip-footer",
            "gzip-crc",
            "gzip-size",
            "gzip-trailing-header",
            "gzip-trailing-deflate",
        ):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    archive_defect=defect, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_source_archive_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_trailing_source_content_rejects_before_consumers(self):
        for defect in (
            "tar-trailing-file",
            "gzip-trailing-file",
            "tar-trailing-duplicate",
            "tar-trailing-bytes",
            "tar-distant-trailing-byte",
        ):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    archive_defect=defect, check_workspace=True, real_consumers=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_source_archive_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_zero_padding_after_source_archive_remains_valid(self):
        payload = source_archive()
        padding = b"\x00" * (2 * 1024 * 1024)
        for padded in (
            payload,
            gzip.compress(gzip.decompress(payload) + padding, mtime=0),
            payload + gzip.compress(padding, mtime=0),
        ):
            with self.subTest(size=len(padded)):
                self.assertEqual(
                    reproduce.validate_source_archive(padded, SOURCE_MANIFEST),
                    json.loads(SOURCE_MANIFEST),
                )

    def test_identical_zip_defects_reject_before_consumers(self):
        for defect in (
            "content",
            "missing",
            "extra",
            "duplicate",
            "empty",
            "launcher",
            "traversal",
            "directory",
            "symlink",
            "special",
            "compressed",
            "crc",
            "truncated",
            "malformed",
        ):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    zip_defect=defect, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_zipapp_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_zip_envelope_rejects_before_consumers(self):
        # These extra bytes are absent from the source manifest, while both
        # synthetic builds and their checksums still agree.
        for defect in (
            "prefix-script",
            "prefix-zero",
            "prefix-archive",
            "suffix-bytes",
            "suffix-zero",
            "suffix-end-record",
            "archive-comment",
        ):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    zip_defect=defect, check_workspace=True, real_consumers=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_zipapp_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_zip_envelope_preserves_binary_members_and_unicode_names(self):
        files = {
            **SOURCE_FILES,
            "aethron/data.bin": b"PK\x05\x06" + b"\x00" * 18 + b"PK\x03\x04",
            "aethron/café.txt": b"binary\x00\xff",
        }
        with patch.dict(SOURCE_FILES, files):
            output, error, consumers, _, _ = self.invoke(real_consumers=True)
        self.assertIsNone(error)
        self.assertEqual(len(consumers), 2)
        self.assertTrue(json.loads(output)["byte_identical_builds"])

    def test_zip_directory_summary_rejects_before_consumers(self):
        # Matching builds/checksums and readable members cannot establish that
        # the end record describes the actual single-disk directory.
        payload = executable_archive()
        directory_size = int.from_bytes(payload[-10:-6], "little")
        directory_offset = int.from_bytes(payload[-6:-2], "little")
        for field, offset, width, value in (
            ("disk", 4, 2, 1),
            ("directory-disk", 6, 2, 1),
            ("disk-count-zero", 8, 2, 0),
            ("disk-count-over", 8, 2, 65535),
            ("total-count-zero", 10, 2, 0),
            ("total-count-over", 10, 2, 65535),
            ("directory-size-short", 12, 4, directory_size - 1),
            ("directory-size-long", 12, 4, directory_size + 1),
            ("directory-offset-before", 16, 4, directory_offset - 1),
            ("directory-offset-after", 16, 4, directory_offset + 1),
        ):
            with self.subTest(field=field):
                output, error, consumers, _, _ = self.invoke(
                    zip_end_record=(offset, width, value),
                    check_workspace=True,
                    real_consumers=True,
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_zipapp_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_unlisted_local_zip_content_rejects_before_consumers(self):
        for defect in (
            "unlisted-middle",
            "unlisted-tail",
            "gap-middle",
            "gap-tail",
            "gap-in-compressed-size",
        ):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    zip_defect=defect, check_workspace=True, real_consumers=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_zipapp_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_zip_local_record_order_is_independent_of_directory_order(self):
        output, error, consumers, _, _ = self.invoke(
            zip_defect="reordered-directory", real_consumers=True
        )
        self.assertIsNone(error)
        self.assertEqual(len(consumers), 2)
        self.assertTrue(json.loads(output)["byte_identical_builds"])

    def test_conflicting_zip_local_headers_reject_before_consumers(self):
        # ZIP readers may trust the central directory and ignore conflicting
        # local CRC, sizes, flags, method, version or timestamps.
        for field, offset, width, value in (
            ("version", 4, 2, 63),
            ("encrypted", 6, 2, 1),
            ("descriptor", 6, 2, 8),
            ("encoding", 6, 2, 2048),
            ("compression", 8, 2, 8),
            ("time", 10, 2, 1),
            ("date", 12, 2, 33),
            ("crc", 14, 4, 0),
            ("compressed-size", 18, 4, 0),
            ("size", 22, 4, 0),
        ):
            with self.subTest(field=field):
                output, error, consumers, _, _ = self.invoke(
                    zip_local_header=(offset, width, value),
                    check_workspace=True,
                    real_consumers=True,
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_zipapp_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_zip_metadata_rejects_before_consumers(self):
        # Equal builds and content hashes cannot validate extraction metadata.
        # These otherwise valid ZIPs also pass the real Python smoke consumers.
        for field, value in (
            ("external_attr", 0o4755 << 16),
            ("external_attr", 0o2755 << 16),
            ("external_attr", 0o666 << 16),
            ("external_attr", 0o755 << 16),
            ("external_attr", (0o644 << 16) | 0x10),
            ("create_system", 0),
            ("create_system", 10),
            ("date_time", (1980, 1, 1, 0, 0, 0)),
            ("date_time", (2026, 1, 1, 0, 0, 2)),
        ):
            with self.subTest(field=field, value=value):
                output, error, consumers, _, _ = self.invoke(
                    zip_metadata={field: value}, check_workspace=True, real_consumers=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_zipapp_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_zip_extension_payloads_reject_before_consumers(self):
        # These ZIPs have correct inventories/content, matching builds/checksums
        # and working Python consumers, but carry bytes absent from source.
        for defect in ("local-extra", "central-extra", "both-extra", "member-comment"):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    zip_defect=defect, check_workspace=True, real_consumers=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_zipapp_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_zip_manifest_binding_protects_files_outside_the_smoke_path(self):
        # Each of these ZIPs still passes both real Python smoke consumers.
        # Inventory/content admission must stop them before those executions.
        for defect in ("content", "missing", "extra", "duplicate"):
            with self.subTest(defect=defect):
                output, error, consumers, _, _ = self.invoke(
                    zip_defect=defect, real_consumers=True, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_zipapp_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_self_consistent_changed_source_rejects_before_real_consumers(self):
        for defect in ("content", "missing", "extra", "renamed"):
            with self.subTest(defect=defect):
                files = dict(SOURCE_FILES)
                if defect == "content":
                    files["aethron/data.bin"] = b"different source bytes"
                elif defect == "missing":
                    del files["aethron/data.bin"]
                elif defect == "extra":
                    files["aethron/extra.bin"] = b"uncommitted file"
                else:
                    files["aethron/renamed.bin"] = files.pop("aethron/data.bin")
                output, error, consumers, _, _ = self.invoke(
                    artifact_files=files, real_consumers=True, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_source_manifest_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_invalid_source_manifests_reject_before_consumers(self):
        digest = hashlib.sha256(SOURCE_FILES["source.txt"]).hexdigest()
        duplicate = ('{"source.txt": "' + digest + '", ' + SOURCE_MANIFEST.decode()[1:]).encode()
        for manifest in (
            b"not JSON",
            b"\xff",
            b"null",
            b"[]",
            b"{}",
            b'{"source.txt": null}',
            b'{"source.txt": true}',
            b'{"source.txt": "wrong digest"}',
            duplicate,
            json.dumps({"source.txt": digest.upper()}).encode(),
            *(
                json.dumps({name: digest}).encode()
                for name in (
                    "",
                    "/source.txt",
                    "../source.txt",
                    "dir/../source.txt",
                    "./source.txt",
                    "dir//source.txt",
                    "dir\\source.txt",
                    "source\x00.txt",
                )
            ),
        ):
            with self.subTest(manifest=manifest):
                output, error, consumers, _, _ = self.invoke(
                    manifest_bytes=manifest, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_source_archive_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_identical_wrong_or_invalid_provenance_rejects_before_consumers(self):
        revision = "a" * 40
        for payload in (
            json.dumps({"source_revision": "b" * 40}).encode(),
            b"{}",
            b"null",
            b"[]",
            b'{"source_revision": null}',
            b'{"source_revision": 1}',
            b"not JSON",
            b"\xff",
            ('{"source_revision":"wrong","source_revision":"' + revision + '"}').encode(),
            ('{"source_revision":"' + revision + '","source_revision":"wrong"}').encode(),
        ):
            with self.subTest(payload=payload):
                output, error, consumers, _, _ = self.invoke(
                    provenance_bytes=payload, check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_provenance_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_provenance_manifest_digest_must_match_compared_bytes(self):
        digest = hashlib.sha256(SOURCE_MANIFEST).hexdigest()
        for value in (None, True, 1, [], {}, "", "0" * 64, digest.upper(), digest + "\n"):
            with self.subTest(value=value):
                provenance = {**PROVENANCE_DECLARATIONS, "source_revision": "a" * 40}
                if value is not None:
                    provenance["source_manifest_sha256"] = value
                output, error, consumers, _, _ = self.invoke(
                    provenance_bytes=json.dumps(provenance).encode(), check_workspace=True
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_provenance_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_changed_manifest_with_consistent_checksums_rejects_stale_provenance(self):
        provenance = {
            **PROVENANCE_DECLARATIONS,
            "source_revision": "a" * 40,
            "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST).hexdigest(),
        }
        output, error, consumers, _, _ = self.invoke(
            provenance_bytes=json.dumps(provenance).encode(),
            manifest_bytes=b"substituted manifest in both builds",
            check_workspace=True,
        )
        self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), "release_provenance_invalid")
        self.assertEqual(output, "")
        self.assertEqual(consumers, [])

    def test_provenance_source_digests_reject_before_real_consumers(self):
        valid = {
            **PROVENANCE_DECLARATIONS,
            "source_revision": "a" * 40,
            "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST).hexdigest(),
            **provenance_sources(SOURCE_FILES),
        }
        cases = []
        for field in ("model_sha256", "data_manifests"):
            missing = dict(valid)
            del missing[field]
            cases.append((field + " missing", missing))
            for value in (None, True, 1, [], {}, "", "0" * 64):
                cases.append((field + " invalid", {**valid, field: value}))
        freezes = valid["data_manifests"]
        cases.extend(
            (name, {**valid, "data_manifests": value})
            for name, value in (
                ("missing freeze", {"data/first/freeze.json": freezes["data/first/freeze.json"]}),
                ("extra freeze", {**freezes, "data/extra/freeze.json": "0" * 64}),
                ("wrong freeze digest", {**freezes, "data/first/freeze.json": "0" * 64}),
                ("non-string digest", {**freezes, "data/first/freeze.json": True}),
                (
                    "renamed freeze",
                    {name.replace("first", "other"): digest for name, digest in freezes.items()},
                ),
                ("swapped digests", dict(zip(freezes, reversed(list(freezes.values()))))),
            )
        )
        for name, provenance in cases:
            with self.subTest(case=name, provenance=provenance):
                output, error, consumers, _, _ = self.invoke(
                    provenance_bytes=json.dumps(provenance).encode(),
                    real_consumers=True,
                    check_workspace=True,
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "release_provenance_invalid")
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_provenance_source_digest_mapping_order_is_irrelevant(self):
        sources = provenance_sources(SOURCE_FILES)
        sources["data_manifests"] = dict(reversed(list(sources["data_manifests"].items())))
        output, error, consumers, _, _ = self.invoke(
            provenance_bytes=json.dumps(
                {
                    **PROVENANCE_DECLARATIONS,
                    **sources,
                    "source_revision": "a" * 40,
                    "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST).hexdigest(),
                }
            ).encode(),
            real_consumers=True,
            check_workspace=True,
        )
        self.assertIsNone(error)
        self.assertTrue(json.loads(output)["byte_identical_builds"])
        self.assertEqual(len(consumers), 2)

    def test_provenance_declarations_reject_before_real_consumers(self):
        valid = {
            **PROVENANCE_DECLARATIONS,
            **provenance_sources(SOURCE_FILES),
            "source_revision": "a" * 40,
            "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST).hexdigest(),
        }
        false_claims = {
            "builder": "different/builder.py",
            "evidence": "signed hosted attestation",
            "runtime_dependencies": "no runtime required",
        }
        for field, expected in PROVENANCE_DECLARATIONS.items():
            for defect in (
                "missing",
                None,
                True,
                1,
                [],
                {},
                "",
                false_claims[field],
                expected + "\n",
            ):
                with self.subTest(field=field, defect=defect):
                    provenance = {**valid, field: defect}
                    if defect == "missing":
                        del provenance[field]
                    output, error, consumers, _, _ = self.invoke(
                        provenance_bytes=json.dumps(provenance).encode(),
                        real_consumers=True,
                        check_workspace=True,
                    )
                    self.assertIsInstance(error, ValueError)
                    self.assertEqual(str(error), "release_provenance_invalid")
                    self.assertEqual(output, "")
                    self.assertEqual(consumers, [])

    def test_provenance_sources_require_model_but_allow_no_frozen_datasets(self):
        digest = hashlib.sha256(b"model fixture").hexdigest()
        provenance = {"model_sha256": digest, "data_manifests": {}}
        reproduce.validate_provenance_sources(provenance, {"aethron/models/rules.json": digest})
        for invalid in (provenance, {"model_sha256": None, "data_manifests": {}}):
            with self.subTest(provenance=invalid):
                with self.assertRaisesRegex(ValueError, "^release_provenance_invalid$"):
                    reproduce.validate_provenance_sources(invalid, {})

    def test_failed_or_terminated_evaluation_cannot_report_overall_success(self):
        for returncode in (1, -15):
            with self.subTest(returncode=returncode):
                output, error, consumers, _, _ = self.invoke(evaluation=returncode)
                self.assertIsInstance(error, SystemExit)
                self.assertNotIn(error.code, (None, 0))
                report = json.loads(output)
                self.assertIs(report["evaluation_gate_passed"], False)
                self.assertIs(report["quickstart"], False)
                self.assertIs(report["byte_identical_builds"], True)
                self.assertIs(report["isolated_zipapp_consumer"], True)
                self.assertEqual(len(consumers), 2)

    def test_artifact_mismatch_stops_before_consumers_and_report(self):
        for mismatch in ("names", "bytes"):
            with self.subTest(mismatch=mismatch):
                output, error, consumers, _, _ = self.invoke(mismatch=mismatch)
                self.assertIsInstance(error, ValueError if mismatch == "names" else AssertionError)
                self.assertEqual(output, "")
                self.assertEqual(consumers, [])

    def test_incomplete_or_extra_inventory_rejects_before_reads_and_consumers(self):
        for lanes in (("a",), ("b",), ("a", "b")):
            for defect in (
                "empty",
                "extra",
                "aethron.pyz",
                "aethron-0.2.0-source.tar.gz",
                "source-manifest.json",
                "sbom.cdx.json",
                "provenance.json",
                "SHA256SUMS",
            ):
                with self.subTest(lanes=lanes, defect=defect):
                    output, error, consumers, _, _ = self.invoke(
                        inventory_defect=defect, inventory_lanes=lanes
                    )
                    self.assertIsInstance(error, ValueError)
                    self.assertEqual(str(error), "release_artifacts_changed")
                    self.assertEqual(output, "")
                    self.assertEqual(consumers, [])

    def test_accepted_dirty_source_cannot_produce_report(self):
        output, error, consumers, _, _ = self.invoke(refusal=0)
        self.assertIsInstance(error, AssertionError)
        self.assertEqual(output, "")
        self.assertEqual(consumers, [])

    def test_failed_consumer_cannot_produce_report(self):
        output, error, consumers, _, _ = self.invoke(consumer=1)
        self.assertIsInstance(error, subprocess.CalledProcessError)
        self.assertEqual(output, "")
        self.assertEqual(len(consumers), 1)

    def test_changed_artifacts_cannot_be_reported_as_compared(self):
        for lane in ("a", "b"):
            for mutation in ("changed", "extra", "removed"):
                for mutate_at in (1, 2):
                    with self.subTest(lane=lane, mutation=mutation, mutate_at=mutate_at):
                        output, error, consumers, _, _ = self.invoke(
                            mutation=mutation, mutate_at=mutate_at, mutate_lane=lane
                        )
                        self.assertIsInstance(error, ValueError)
                        self.assertEqual(str(error), "release_artifacts_changed")
                        self.assertEqual(output, "")
                        self.assertEqual(len(consumers), mutate_at)

    def test_linked_artifacts_cannot_be_reported_as_compared(self):
        for lane in ("a", "b"):
            for mutation in ("file_link", "directory_link"):
                for mutate_at in (1, 2):
                    with self.subTest(lane=lane, mutation=mutation, mutate_at=mutate_at):
                        output, error, consumers, _, _ = self.invoke(
                            mutation=mutation, mutate_at=mutate_at, mutate_lane=lane
                        )
                        self.assertIsInstance(error, ValueError)
                        self.assertEqual(str(error), "release_artifacts_changed")
                        self.assertEqual(output, "")
                        self.assertEqual(len(consumers), mutate_at)

    def test_linked_build_outputs_are_rejected_before_consumers(self):
        for lane in ("a", "b"):
            for mutation in ("file_link", "directory_link"):
                with self.subTest(lane=lane, mutation=mutation):
                    output, error, consumers, _, _ = self.invoke(
                        mutation=mutation, mutate_at=0, mutate_lane=lane
                    )
                    self.assertIsInstance(error, ValueError)
                    self.assertEqual(str(error), "release_artifacts_changed")
                    self.assertEqual(output, "")
                    self.assertEqual(consumers, [])

    def test_invalid_build_outputs_are_rejected_before_payload_reads(self):
        mutations = ["file_link", "directory_link", "directory_entry"]
        if hasattr(os, "mkfifo"):
            mutations.append("fifo")
        for lane in ("a", "b"):
            for mutation in mutations:
                with self.subTest(lane=lane, mutation=mutation):
                    output, error, consumers, _, _ = self.invoke(
                        mutation=mutation,
                        mutate_at=0,
                        mutate_lane=lane,
                        guard_artifact_reads=True,
                    )
                    self.assertIsInstance(error, ValueError)
                    self.assertEqual(str(error), "release_artifacts_changed")
                    self.assertEqual(output, "")
                    self.assertEqual(consumers, [])

    def test_zip_consumers_ignore_caller_import_path(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "aethron"
            package.mkdir()
            (package / "__init__.py").write_text(
                "raise RuntimeError('caller package imported')\n", encoding="utf-8"
            )
            # An unrelated caller module must not be visible to the archive.
            (Path(directory) / "zip_shadow.py").write_text(
                "raise RuntimeError('caller import path leaked')\n", encoding="utf-8"
            )
            for variable in ("PYTHONHOME", "PYTHONPATH"):
                with self.subTest(variable=variable), patch.dict(os.environ, {variable: directory}):
                    output, error, consumers, _, _ = self.invoke(real_consumers=True)
                    self.assertIsNone(error)
                    self.assertEqual(len(consumers), 2)
                    self.assertIs(json.loads(output)["isolated_zipapp_consumer"], True)

    def test_all_python_stages_ignore_inherited_home_and_path(self):
        for home in ("missing", "existing", None):
            with self.subTest(home=home), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                foreign_home = root / "foreign-home"
                if home == "existing":
                    foreign_home.mkdir()
                foreign_path = root / "foreign-path"
                foreign_path.mkdir()
                (foreign_path / "sitecustomize.py").write_text(
                    "raise SystemExit('foreign sitecustomize executed')\n", encoding="utf-8"
                )
                (foreign_path / "caller_shadow.py").write_text("", encoding="utf-8")
                inherited = dict(os.environ)
                inherited.pop("PYTHONHOME", None)
                if home is not None:
                    inherited["PYTHONHOME"] = str(foreign_home)
                inherited["PYTHONPATH"] = str(foreign_path)
                inherited["AETHRON_REPRODUCTION_TEST"] = "preserved"
                probes = []
                with patch.dict(os.environ, inherited, clear=True):
                    output, error, consumers, _, _ = self.invoke(
                        python_probes=probes, real_consumers=True
                    )
                    self.assertEqual(dict(os.environ), inherited)
                self.assertIsNone(error)
                self.assertEqual(len(probes), 10)
                self.assertEqual(len(consumers), 2)
                self.assertIs(json.loads(output)["quickstart"], True)
