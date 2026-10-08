"""Build two CPU architectures and exercise installed HTTP/SSE without WAN."""

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run():
    area = ROOT / "build/ecosystem-phase1"
    context = area / "container-context"
    context.mkdir(exist_ok=True)
    (context / "wheels").mkdir(exist_ok=True)
    for wheel in (area / "package/a").glob("*.whl"):
        shutil.copyfile(wheel, context / "wheels" / wheel.name)
    for name in ("requirements-server.lock", "requirements-vision.lock"):
        shutil.copyfile(ROOT / "integrations/edge" / name, context / name)
    shutil.copyfile(ROOT / "integrations/edge/container/Containerfile", context / "Containerfile")
    env = dict(os.environ, BUILDX_CONFIG=str(area / "buildx"))
    tag = "aethron-edge-phase1:local"
    subprocess.run(
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            "linux/arm64,linux/amd64",
            "--load",
            "-t",
            tag,
            "-f",
            str(context / "Containerfile"),
            str(context),
        ],
        env=env,
        check=True,
    )
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", tag], text=True
    ).strip()
    results = []
    for arch in ("arm64", "amd64"):
        completed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/" + arch,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--memory",
                "768m",
                "--cpus",
                "2",
                "--tmpfs",
                "/work:uid=10001,gid=10001,mode=0700",
                "--tmpfs",
                "/tmp",
                "--entrypoint",
                "python",
                "-v",
                str(ROOT / "examples/temporal-blackout.jsonl") + ":/fixture.jsonl:ro",
                "-v",
                str(ROOT / "packaging/appliance/container_probe.py") + ":/probe.py:ro",
                tag,
                "-B",
                "/probe.py",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        result = json.loads(completed.stdout)
        result.update(
            platform="linux/" + arch,
            image=image_id,
            execution="Docker Linux VM; amd64 emulated on this ARM host",
        )
        results.append(result)
    (area / "containers.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))


if __name__ == "__main__":
    run()
