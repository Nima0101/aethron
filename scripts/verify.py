"""Offline mandatory software checks. Full fuzz/security/release checks documented separately."""

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run():
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
        doc = json.loads((ROOT / "docs/verification" / manifest).read_text(encoding="utf-8"))
        for name, digest in doc["files"].items():
            actual = (
                "docs/engineering/history/AGENTS.v1.md"
                if manifest == "governance-freeze.json" and name == "AGENTS.md"
                else "docs/engineering/history/AGENTS.v2.md"
                if manifest == "amendment-v2-freeze.json" and name == "AGENTS.md"
                else name
            )
            assert hashlib.sha256((ROOT / actual).read_bytes()).hexdigest() == digest, (
                "freeze mismatch: " + name
            )
    for p in ROOT.joinpath("aethron").rglob("*.py"):
        assert not re.search(r"\b(?:TO" + "DO|FIX" + "ME)\b", p.read_text(encoding="utf-8")), p.name
        tree = ast.parse(p.read_text(encoding="utf-8"))
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
    tracked = set(
        subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    )
    # Scan only intended product files; never inspect local credentials/environment.
    for folder in [
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
        "",
    ]:
        for p in ROOT.joinpath(folder).rglob("*") if folder else ROOT.iterdir():
            if not p.is_file():
                continue
            relative = p.relative_to(ROOT)
            if {"__pycache__", "node_modules", "build"}.intersection(relative.parts) and str(
                relative
            ) not in tracked:
                continue
            if p.suffix not in {
                ".py",
                ".md",
                ".json",
                ".jsonl",
                ".yml",
                ".yaml",
                ".svg",
                ".html",
                ".txt",
            }:
                continue
            text = p.read_text(encoding="utf-8")
            for forbidden in [
                "/Users/",
                "/home/",
                "BEGIN PRIVATE KEY",
                "ghp_" + "[A-Za-z0-9]{30,}",
                "AKIA" + "[A-Z0-9]{16}",
            ]:
                # Scanner patterns themselves are not leaks.
                if p.name != "verify.py":
                    assert re.search(forbidden, text) is None, "public leak: " + str(
                        p.relative_to(ROOT)
                    )
            if p.suffix == ".md":
                for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
                    if "://" in link or link.startswith("#"):
                        continue
                    target = link.split("#")[0]
                    assert (p.parent / target).exists(), (
                        "broken link: " + str(p.relative_to(ROOT)) + " " + link
                    )
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, check=True
    )
    subprocess.run([sys.executable, "scripts/evaluate_dataset.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/consumer.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/temporal_e2e.py"], cwd=ROOT, check=True)
    print(
        "PASS: governance, bounded-runtime static policy, public-content/links, tests, dataset, consumer"
    )


if __name__ == "__main__":
    run()
