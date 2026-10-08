"""Clean clone, exact README quickstart, isolated consumer and two release builds."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def call(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, check=True, **kw)


def run():
    with tempfile.TemporaryDirectory(prefix="aethron-clean-") as temporary:
        root = Path(temporary)
        clone = root / "source"
        call(["git", "clone", "--no-local", str(ROOT), str(clone)], ROOT, capture_output=True)
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
        a, b = root / "a", root / "b"
        assert sorted(p.name for p in a.iterdir()) == sorted(p.name for p in b.iterdir())
        for p in a.iterdir():
            assert p.read_bytes() == (b / p.name).read_bytes(), p.name
        call(
            [
                sys.executable,
                str(a / "aethron.pyz"),
                "evaluate",
                str(clone / "examples/person-blackout.json"),
            ],
            root,
            stdout=subprocess.DEVNULL,
        )
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
        result = {
            "source_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=clone, text=True
            ).strip(),
            "clean_clone": True,
            "evaluation_gate_passed": evaluation.returncode == 0,
            "quickstart": evaluation.returncode == 0,
            "isolated_zipapp_consumer": True,
            "byte_identical_builds": True,
            "artifact_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in a.iterdir()
            },
        }
        print(json.dumps(result, sort_keys=True))
        if evaluation.returncode != 0:
            raise SystemExit("evaluation gate failed; independent packaging checks completed")


if __name__ == "__main__":
    run()
