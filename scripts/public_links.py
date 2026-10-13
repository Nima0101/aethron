"""Check Markdown link closure in an immutable Git tree before publication.

Only reads Git objects; never includes missing files or approves their content.
Link syntax matches scripts/verify.py; nonlocal and fragment-only links skip.
"""

import argparse
import json
import os
import posixpath
import subprocess
from pathlib import Path

if __package__:
    from .git_context import GIT_COMMAND_TIMEOUT_SECONDS, git_output, require_default_git_context
    from .markdown_links import local_destinations
else:
    from git_context import GIT_COMMAND_TIMEOUT_SECONDS, git_output, require_default_git_context
    from markdown_links import local_destinations


# Developer-tool admission budgets, not product or measured hardware limits.
MAX_TREE_ENTRIES = 10_000
MAX_MARKDOWN_DOCUMENTS = 1_000
MAX_MARKDOWN_BYTES = 1024 * 1024
MAX_TOTAL_MARKDOWN_BYTES = 16 * 1024 * 1024
MAX_LOCAL_DESTINATIONS = 10_000
MAX_MISSING_PATH_BYTES = 1024 * 1024


def check(repo, revision):
    # Reading an incomplete repository must not fetch or modify its object store.
    git_env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": ""}
    require_default_git_context(git_env)

    def git(*args):
        # A report naming an object ID must inspect that object, not refs/replace.
        return git_output(
            ["git", "--no-replace-objects", *args],
            cwd=repo,
            env=git_env,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )

    tree = git("rev-parse", "--verify", "--end-of-options", revision + "^{tree}").decode().strip()
    inventory = git("ls-tree", "-r", "-t", "-z", "--full-tree", tree)
    if inventory and not inventory.endswith(b"\0"):
        raise ValueError("invalid_public_inventory")
    if inventory.count(b"\0") > MAX_TREE_ENTRIES:
        raise ValueError("public_tree_limit")
    entries = {}
    for entry in inventory.split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            entries[name.decode("utf-8")] = (mode, kind, oid)
    missing = []
    documents = total_bytes = destinations = missing_bytes = 0
    for name, (mode, kind, oid) in sorted(entries.items()):
        if (mode, kind) == ("040000", "tree"):
            continue  # Directory suffixes do not make them Markdown documents.
        if not name.endswith(".md"):
            continue
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError("unsupported_markdown_entry")
        documents += 1
        if documents > MAX_MARKDOWN_DOCUMENTS:
            raise ValueError("public_tree_limit")
        body = git("cat-file", "blob", oid)
        total_bytes += len(body)
        if len(body) > MAX_MARKDOWN_BYTES or total_bytes > MAX_TOTAL_MARKDOWN_BYTES:
            raise ValueError("public_tree_limit")
        text = body.decode("utf-8")
        for link in local_destinations(text):
            destinations += 1
            if destinations > MAX_LOCAL_DESTINATIONS:
                raise ValueError("public_tree_limit")
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
            if target != "." and (
                target not in entries or entries[target][0] not in ("040000", "100644", "100755")
            ):
                missing_bytes += len(name.encode("utf-8")) + len(target.encode("utf-8"))
                if missing_bytes > MAX_MISSING_PATH_BYTES:
                    raise ValueError("public_tree_limit")
                missing.append({"source": name, "target": target})
    return {"tree": tree, "missing": missing}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="Commit or tree to inspect; no worktree fallback")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        report = check(args.repo, args.revision)
    except (
        OSError,
        ValueError,
        RecursionError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        parser.exit(2, "invalid_public_tree\n")
    print(json.dumps(report, sort_keys=True))
    return int(bool(report["missing"]))


if __name__ == "__main__":
    raise SystemExit(main())
