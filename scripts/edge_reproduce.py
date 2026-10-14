"""Clean local clone builds and installs the committed candidate; no public operation."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

if __package__:
    from .git_context import GIT_COMMAND_TIMEOUT_SECONDS, require_default_git_context
    from .reproduce import (
        GIT_CLONE_TIMEOUT_SECONDS,
        VERIFICATION_TIMEOUT_SECONDS,
        reproduction_workspace,
        validate_source,
    )
else:
    from git_context import GIT_COMMAND_TIMEOUT_SECONDS, require_default_git_context
    from reproduce import (
        GIT_CLONE_TIMEOUT_SECONDS,
        VERIFICATION_TIMEOUT_SECONDS,
        reproduction_workspace,
        validate_source,
    )

ROOT = Path(__file__).resolve().parents[1]


def run(wheelhouse):
    require_default_git_context(os.environ)
    area = ROOT / "build/ecosystem-phase1"
    area.mkdir(parents=True, exist_ok=True)
    with reproduction_workspace(prefix="clean-edge-", dir=area) as temporary:
        clone = Path(temporary) / "source"
        subprocess.run(
            ["git", "clone", "--no-local", str(ROOT), str(clone)],
            check=True,
            capture_output=True,
            timeout=GIT_CLONE_TIMEOUT_SECONDS,
        )
        revision = subprocess.check_output(
            ["git", "--no-replace-objects", "rev-parse", "HEAD"],
            cwd=clone,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        ).strip()
        validate_source(clone, revision)
        # User-site .pth/customization hooks run before a script and can exit
        # successfully without executing any verification. Keep tooling in the
        # selected interpreter environment, with user-site startup disabled.
        env = dict(os.environ, PYTHONNOUSERSITE="1")
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        # Same per-child tooling budgets as core reproduction, not a whole-run
        # deadline or a guarantee of descendant-process cleanup.
        subprocess.run(
            [sys.executable, "scripts/verify.py"],
            cwd=clone,
            env=env,
            check=True,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
        )
        validate_source(clone, revision)
        subprocess.run(
            [sys.executable, "scripts/check_ecosystem_plan.py", "--self-test"],
            cwd=clone,
            env=env,
            check=True,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
        )
        validate_source(clone, revision)
        # Each attempt owns separate persistent evidence, outside clone cleanup.
        # The package checker still refuses to reuse any existing output directory.
        package = area / (clone.parent.name + "-package")
        print(f"package evidence directory: {package}", file=sys.stderr)
        subprocess.run(
            [
                sys.executable,
                "scripts/edge_package_check.py",
                "--wheelhouse",
                str(wheelhouse.resolve()),
                "--out",
                str(package),
            ],
            cwd=clone,
            env=env,
            check=True,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
        )
        validate_source(clone, revision)
        print("PASS: committed clean clone and installed consumer; local artifacts only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheelhouse", type=Path, default=ROOT / "build/ecosystem-phase1/wheelhouse"
    )
    run(parser.parse_args().wheelhouse)
