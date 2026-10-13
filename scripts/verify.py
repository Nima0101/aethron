"""Offline mandatory software checks. Full fuzz/security/release checks documented separately."""

import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

# Optimized execution removes the assertions that establish this evidence.
if sys.flags.optimize:
    raise SystemExit("verify_requires_assertions")

if __package__:
    from .git_context import GIT_COMMAND_TIMEOUT_SECONDS, git_output, require_default_git_context
else:
    from git_context import GIT_COMMAND_TIMEOUT_SECONDS, git_output, require_default_git_context

ROOT = Path(__file__).resolve().parents[1]
SCAN_FOLDERS = (
    "aethron",
    "integrations",
    "packaging",
    "contracts",
    "tests",
    "scripts",
    "docs",
    "examples",
    "data",
    ".github",
)
TEXT_SUFFIXES = {".py", ".md", ".json", ".jsonl", ".yml", ".yaml", ".svg", ".html", ".txt"}
# Content-scan admission budgets, not whole-verifier resource guarantees.
MAX_WORKTREE_MARKDOWN_BYTES = 1024 * 1024
MAX_WORKTREE_MARKDOWN_TOTAL_BYTES = 16 * 1024 * 1024
MAX_WORKTREE_MARKDOWN_DOCUMENTS = 1000
MAX_WORKTREE_LOCAL_DESTINATIONS = 10000
FREEZE_HASH_CHUNK_BYTES = 64 * 1024
MAX_FREEZE_MANIFEST_BYTES = 1024 * 1024
MAX_FREEZE_MANIFEST_ENTRIES = 10000
MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 16 * 1024 * 1024
MAX_OTHER_TEXT_BYTES = 8 * 1024 * 1024
MAX_OTHER_TEXT_TOTAL_BYTES = 64 * 1024 * 1024
MAX_TRAVERSAL_ENTRIES = 100000
MAX_TRAVERSAL_DEPTH = 64


def require_worktree_root():
    """Keep repository-relative inventory aligned with this scan's root."""
    require_default_git_context(os.environ)
    context = git_output(
        ["git", "rev-parse", "--is-inside-work-tree", "--show-prefix"],
        cwd=ROOT,
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
    )
    if context != b"true\n\n":
        raise ValueError("invalid_verification_root")


def tracked_files():
    require_worktree_root()
    data = git_output(
        ["git", "ls-files", "--cached", "--full-name", "-z"],
        cwd=ROOT,
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
    )
    if not data:
        return set()
    if not data.endswith(b"\0"):
        raise ValueError("invalid tracked inventory")
    try:
        names = data[:-1].decode("utf-8").split("\0")
    except UnicodeDecodeError:
        raise ValueError("invalid tracked inventory") from None
    for name in names:
        path = PurePosixPath(name)
        if (
            not name
            or name == "."
            or path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != name
        ):
            raise ValueError("invalid tracked inventory")
    return set(names)


def content_candidate(relative):
    return relative.suffix in TEXT_SUFFIXES and (
        len(relative.parts) == 1 or relative.parts[0] in SCAN_FOLDERS
    )


def local_path(path):
    """Reject escapes and redirecting entries in a stable, trusted checkout."""
    root = Path(ROOT)
    try:
        parts = Path(path).relative_to(root).parts
    except ValueError:
        raise AssertionError("unsafe repository path") from None
    current = root
    for part in parts:
        if part == "..":
            assert current != root, "unsafe repository path"
            current = current.parent
            continue
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        assert not stat.S_ISLNK(info.st_mode), "unsafe repository path"
        # Includes Windows junctions, also on Python versions before is_junction.
        assert not getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
        ), "unsafe repository path"
    return path


def local_bytes(path, *, max_bytes=None, limit_error="worktree_markdown_limit"):
    path = local_path(path)
    info = path.stat()
    assert stat.S_ISREG(info.st_mode), "unsafe repository path"
    if max_bytes is None:
        return path.read_bytes()
    if info.st_size > max_bytes:
        raise ValueError(limit_error)
    # The extra byte detects growth since stat without an unbounded allocation.
    with path.open("rb") as stream:
        body = stream.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError(limit_error)
    return body


def unique_manifest_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("invalid_freeze_manifest")
        fields[key] = value
    return fields


def freeze_files(path):
    """Admit a bounded, unambiguous inventory before opening its payloads."""
    body = local_bytes(
        path, max_bytes=MAX_FREEZE_MANIFEST_BYTES, limit_error="freeze_manifest_limit"
    )
    doc = json.loads(body.decode("utf-8"), object_pairs_hook=unique_manifest_fields)
    if not isinstance(doc, dict) or not isinstance(doc.get("files"), dict):
        raise ValueError("invalid_freeze_manifest")
    files = doc["files"]
    if len(files) > MAX_FREEZE_MANIFEST_ENTRIES:
        raise ValueError("freeze_manifest_limit")
    for name, digest in files.items():
        if not name or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("invalid_freeze_manifest")
    return files


def local_sha256(path):
    """Hash a regular checkout file without allocating its complete contents."""
    path = local_path(path)
    assert stat.S_ISREG(path.stat().st_mode), "unsafe repository path"
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(FREEZE_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class _TraversalBudget:
    def __init__(self):
        self.entries = 0

    def admit(self, path, base):
        self.entries += 1
        if (
            self.entries > MAX_TRAVERSAL_ENTRIES
            or len(path.relative_to(base).parts) > MAX_TRAVERSAL_DEPTH
        ):
            raise ValueError("worktree_traversal_limit")


def working_files(base, *, included=None, recursive=True, budget=None):
    """Enumerate selected files without suppressing filesystem errors."""
    base = local_path(base)
    try:
        mode = base.stat().st_mode
    except FileNotFoundError:
        # Some configured directories are optional in a checkout.
        return
    if not stat.S_ISDIR(mode):
        raise NotADirectoryError(str(base))
    if budget is None:
        budget = _TraversalBudget()
    pending = [base]
    while pending:
        directory = local_path(pending.pop())
        with os.scandir(directory) as entries:
            for entry in entries:
                path = directory / entry.name
                budget.admit(path, base)
                relative = path.relative_to(ROOT)
                if (
                    included is not None
                    and {"__pycache__", "node_modules", "build"}.intersection(relative.parts)
                    and relative.as_posix() not in included
                ):
                    continue
                mode = local_path(path).stat().st_mode
                if stat.S_ISDIR(mode):
                    if recursive:
                        pending.append(path)
                elif stat.S_ISREG(mode):
                    yield path


def run():
    if __package__:
        from .markdown_links import local_destinations
    else:
        from markdown_links import local_destinations

    require_default_git_context(os.environ)
    require_worktree_root()
    subprocess.run([sys.executable, "scripts/public_links.py", "HEAD"], cwd=ROOT, check=True)
    for manifest in [
        "governance-freeze.json",
        "architecture-freeze.json",
        "amendment-v2-freeze.json",
        "data-freeze.json",
        "amendment-v3-freeze.json",
        "data-v3-freeze.json",
        "registration-freeze.json",
        "rgb-model-freeze.json",
        "rgb-smoke-freeze.json",
    ]:
        files = freeze_files(ROOT / "docs/verification" / manifest)
        for name, digest in files.items():
            actual = (
                "docs/engineering/history/AGENTS.v1.md"
                if manifest == "governance-freeze.json" and name == "AGENTS.md"
                else "docs/engineering/history/AGENTS.v2.md"
                if manifest == "amendment-v2-freeze.json" and name == "AGENTS.md"
                else name
            )
            assert local_sha256(ROOT / actual) == digest, "freeze mismatch: " + name
    traversal_budget = _TraversalBudget()
    source_bytes = 0
    for p in working_files(ROOT / "aethron", budget=traversal_budget):
        if not p.match("*.py"):
            continue
        body = local_bytes(
            p,
            max_bytes=min(MAX_SOURCE_BYTES, MAX_SOURCE_TOTAL_BYTES - source_bytes),
            limit_error="source_scan_limit",
        )
        source_bytes += len(body)
        source = body.decode("utf-8")
        assert not re.search(r"\b(?:TO" + "DO|FIX" + r"ME)\b", source), p.name
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [n.name for n in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                assert not any(
                    n.split(".")[0]
                    in {"socket", "requests", "urllib", "pickle", "subprocess", "ctypes"}
                    for n in names
                ), p.name
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile"}, p.name
    # Generated dependency trees are excluded only when untracked. A tracked
    # product file cannot evade the leak gate by using a generated directory name.
    tracked = tracked_files()
    expected = {name for name in tracked if content_candidate(PurePosixPath(name))}
    scanned = set()
    included = tracked | {
        parent.as_posix() for name in tracked for parent in PurePosixPath(name).parents
    }
    markdown_documents = markdown_bytes = local_destinations_seen = 0
    other_text_bytes = 0
    # Scan only intended product files; never inspect local credentials/environment.
    for folder in (*SCAN_FOLDERS, ""):
        for p in working_files(
            ROOT / folder, included=included, recursive=bool(folder), budget=traversal_budget
        ):
            relative = p.relative_to(ROOT)
            if not content_candidate(relative):
                continue
            if p.suffix == ".md":
                markdown_documents += 1
                if markdown_documents > MAX_WORKTREE_MARKDOWN_DOCUMENTS:
                    raise ValueError("worktree_markdown_limit")
                body = local_bytes(
                    p,
                    max_bytes=min(
                        MAX_WORKTREE_MARKDOWN_BYTES,
                        MAX_WORKTREE_MARKDOWN_TOTAL_BYTES - markdown_bytes,
                    ),
                )
                markdown_bytes += len(body)
                text = body.decode("utf-8")
            else:
                body = local_bytes(
                    p,
                    max_bytes=min(
                        MAX_OTHER_TEXT_BYTES, MAX_OTHER_TEXT_TOTAL_BYTES - other_text_bytes
                    ),
                    limit_error="content_scan_limit",
                )
                other_text_bytes += len(body)
                text = body.decode("utf-8")
            for forbidden in [
                "/Users/",
                "/home/",
                "BEGIN PRIVATE KEY",
                "ghp_" + "[A-Za-z0-9]{30,}",
                "AKIA" + "[A-Z0-9]{16}",
            ]:
                # Scanner patterns themselves are not leaks.
                if relative.as_posix() != "scripts/verify.py":
                    assert re.search(forbidden, text) is None, "public leak: " + str(
                        p.relative_to(ROOT)
                    )
            if p.suffix == ".md":
                for target in local_destinations(text):
                    local_destinations_seen += 1
                    if local_destinations_seen > MAX_WORKTREE_LOCAL_DESTINATIONS:
                        raise ValueError("worktree_markdown_limit")
                    assert local_path(p.parent / target).exists(), (
                        "broken link: " + str(p.relative_to(ROOT)) + " " + target
                    )
            scanned.add(relative.as_posix())
    assert expected <= scanned, "missing tracked content"
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, check=True
    )
    subprocess.run([sys.executable, "scripts/evaluate_dataset.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/consumer.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/temporal_e2e.py"], cwd=ROOT, check=True)
    print(
        "PASS: freeze hashes, source syntax rules, public-content/links, "
        "tests, dataset, consumer, temporal E2E"
    )


if __name__ == "__main__":
    run()
