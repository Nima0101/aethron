"""Clean clone, exact README quickstart, isolated consumer and two release builds."""

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
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


def validate_source(clone, revision):
    """Bind sequential checks to one clean revision, excluding ignored build outputs."""
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


@contextlib.contextmanager
def reproduction_workspace():
    """Retain failed runs for diagnosis; only successful runs own automatic cleanup."""
    temporary = tempfile.mkdtemp(prefix="aethron-clean-")
    try:
        yield temporary
    except BaseException:
        # Includes evaluation SystemExit and operator interruption.
        print(f"reproduction evidence retained at: {temporary}", file=sys.stderr)
        raise
    else:
        shutil.rmtree(temporary)


def run():
    with reproduction_workspace() as temporary:
        root = Path(temporary)
        clone = root / "source"
        call(["git", "clone", "--no-local", str(ROOT), str(clone)], ROOT, capture_output=True)
        revision = subprocess.check_output(
            ["git", "--no-replace-objects", "rev-parse", "HEAD"], cwd=clone, text=True
        ).strip()
        validate_source(clone, revision)
        # Quickstart commands as documented, with the active Python interpreter.
        call([sys.executable, "scripts/verify.py"], clone)
        evaluation = subprocess.run(
            [sys.executable, "scripts/temporal_evaluate.py", "--out", str(root / "evaluation")],
            cwd=clone,
            check=False,
        )
        with (root / "demo.jsonl").open("w") as stream:
            call([sys.executable, "-m", "aethron", "demo"], clone, stdout=stream)
        with (root / "result.json").open("w") as stream:
            call(
                [sys.executable, "-m", "aethron", "evaluate", "examples/person-blackout.json"],
                clone,
                stdout=stream,
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
            )
        validate_source(clone, revision)
        probe = clone / "aethron" / "untracked_release_probe.py"
        probe.write_text("# An untracked runtime change must block release.\n", encoding="utf-8")
        refused = subprocess.run(
            [sys.executable, "scripts/release.py", str(root / "refused")],
            cwd=clone,
            capture_output=True,
            check=False,
        )
        assert refused.returncode != 0 and b"clean committed source" in refused.stderr
        probe.unlink()
        call([sys.executable, "scripts/release.py", str(root / "a")], clone)
        call([sys.executable, "scripts/release.py", str(root / "b")], clone)
        validate_source(clone, revision)
        a, b = root / "a", root / "b"
        paths_a, paths_b = artifact_paths(a), artifact_paths(b)
        assert [p.name for p in paths_a] == [p.name for p in paths_b]
        artifact_manifest = {}
        for p in paths_a:
            compared = p.read_bytes()
            assert compared == (b / p.name).read_bytes(), p.name
            artifact_manifest[p.name] = hashlib.sha256(compared).hexdigest()
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
        )
        for directory in (a, b):
            validate_artifacts(directory, artifact_manifest)
        validate_source(clone, revision)
        # zipimport consumer from outside the checkout, no PYTHONPATH dependency.
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
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
