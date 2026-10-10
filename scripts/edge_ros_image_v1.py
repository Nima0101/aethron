"""Acquire the frozen ROS CI image; never starts a container. Hosted execution only."""

import argparse
import json
import os
import re

# Only fixed Docker operations below; no shell or caller-supplied executable.
import subprocess  # nosec B404
import tempfile
from pathlib import Path

IMAGE = "ros@sha256:8f687fdf084482819aa7dab48c3887331edd0d3687b219951fdb66c418316ab1"
PLATFORM = "linux/arm64"
_USER = "AETHRON_DOCKERHUB_USERNAME"
# Environment variable name, not a credential value.
_TOKEN = "AETHRON_DOCKERHUB_TOKEN"  # nosec B105


def _command(command, record, env, *, timeout, input_data=None):
    record["exit_code"] = None
    with tempfile.TemporaryFile() as output:
        try:
            # Fixed Docker CLI argv; optional username is validated before use.
            completed = subprocess.run(  # nosec B603
                command,
                input=input_data,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            record["reason"] = "timeout"
            raise RuntimeError("image_acquisition_failed") from None
        except OSError:
            record["reason"] = "runtime_failed"
            raise RuntimeError("image_acquisition_failed") from None
        record["exit_code"] = completed.returncode
        output.seek(0)
        raw = output.read(65537)
        if completed.returncode:
            limited = b"toomanyrequests" in raw.lower() or b"pull rate limit" in raw.lower()
            record["reason"] = (
                "rate_limited" if record["stage"] == "pull" and limited else "command_failed"
            )
            raise RuntimeError("image_acquisition_failed")
        if len(raw) > 65536:
            record["reason"] = "output_limit"
            raise RuntimeError("image_acquisition_failed")
        return raw


def acquire(out: Path):
    out.mkdir(parents=True, exist_ok=False)
    record = {
        "version": 1,
        "image": IMAGE,
        "platform": PLATFORM,
        "state": "failed",
        "stage": "configuration",
        "reason": "incomplete",
        "authentication": "anonymous",
        "exit_code": None,
    }
    result = out / "result.json"
    result.write_text(json.dumps(record, indent=2) + "\n")
    try:
        username, token = os.environ.get(_USER, ""), os.environ.get(_TOKEN, "")
        if username or token:
            record["authentication"] = "requested"
            if (
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", username)
                or not 1 <= len(token) <= 4096
                or not all(33 <= ord(char) <= 126 for char in token)
            ):
                record["reason"] = "invalid_credentials"
                raise RuntimeError("image_acquisition_failed")
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {_USER, _TOKEN, "DOCKER_AUTH_CONFIG", "DOCKER_CONFIG"}
        }
        with tempfile.TemporaryDirectory(prefix="aethron-ros-auth-") as directory:
            # A nonempty auth map suppresses Docker's automatic host credential
            # helper discovery. The empty entry has no credential authority.
            config = Path(directory) / "config.json"
            config.write_text('{"auths":{"https://index.docker.io/v1/":{}}}\n')
            config.chmod(0o600)
            command = ["docker", "--config", directory]
            if username:
                record["stage"] = "login"
                _command(
                    command + ["login", "docker.io", "--username", username, "--password-stdin"],
                    record,
                    env,
                    timeout=30,
                    input_data=(token + "\n").encode("ascii"),
                )
                record["authentication"] = "authenticated"
            record["stage"] = "pull"
            _command(
                command + ["pull", "--quiet", "--platform", PLATFORM, IMAGE],
                record,
                env,
                timeout=180,
            )
            record["stage"] = "inspect"
            platform = _command(
                command + ["image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", IMAGE],
                record,
                env,
                timeout=15,
            )
            if platform.strip() != PLATFORM.encode("ascii"):
                record["reason"] = "platform_mismatch"
                raise RuntimeError("image_acquisition_failed")
        record.update(state="acquired", reason="verified")
        return record
    finally:
        result.write_text(json.dumps(record, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        acquire(args.out)
    except (OSError, RuntimeError):
        parser.exit(2, "image_acquisition_failed\n")


if __name__ == "__main__":
    main()
