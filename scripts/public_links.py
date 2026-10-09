"""Check inline Markdown link closure in an immutable Git tree before publication.

Only reads Git objects; never includes missing files or approves their content.
Link syntax matches scripts/verify.py; remote URLs and fragment-only links skip.
"""

import argparse
import json
import posixpath
import re
import subprocess
from pathlib import Path


def check(repo, revision):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.PIPE)

    tree = git("rev-parse", "--verify", "--end-of-options", revision + "^{tree}").decode().strip()
    entries = {}
    for entry in git("ls-tree", "-r", "-t", "-z", "--full-tree", tree).split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            entries[name.decode("utf-8")] = (mode, kind, oid)
    missing = []
    for name, (mode, kind, oid) in sorted(entries.items()):
        if not name.endswith(".md"):
            continue
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError("unsupported_markdown_entry")
        text = git("cat-file", "blob", oid).decode("utf-8")
        for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
            if "://" in link or link.startswith("#"):
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), link.split("#")[0]))
            if target != "." and (
                target not in entries or entries[target][0] not in ("040000", "100644", "100755")
            ):
                missing.append({"source": name, "target": target})
    return {"tree": tree, "missing": missing}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="Commit or tree to inspect; no worktree fallback")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        report = check(args.repo, args.revision)
    except (OSError, ValueError, subprocess.CalledProcessError):
        parser.exit(2, "invalid_public_tree\n")
    print(json.dumps(report, sort_keys=True))
    return int(bool(report["missing"]))


if __name__ == "__main__":
    raise SystemExit(main())
