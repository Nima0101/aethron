"""Docker process-boundary fixtures only: never run a local Docker daemon."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "ros@sha256:8f687fdf084482819aa7dab48c3887331edd0d3687b219951fdb66c418316ab1"


class ImageAcquisitionTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "scripts/edge_ros_image_v1.py"
        self.assertTrue(path.is_file(), "missing acquisition helper")
        spec = importlib.util.spec_from_file_location("ros_image", path)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "evidence"
        self.commands = []
        self.configs = []

    def docker(self, command, **kwargs):
        self.commands.append(command)
        config = Path(command[2])
        self.configs.append(config)
        self.assertEqual(config.stat().st_mode & 0o777, 0o700)
        self.assertNotIn("AETHRON_DOCKERHUB_TOKEN", kwargs["env"])
        self.assertNotIn("AETHRON_DOCKERHUB_USERNAME", kwargs["env"])
        self.assertNotIn("DOCKER_AUTH_CONFIG", kwargs["env"])
        self.assertNotIn("DOCKER_CONFIG", kwargs["env"])
        self.assertEqual((config / "config.json").stat().st_mode & 0o777, 0o600)
        if len(self.commands) == 1:
            self.assertEqual(
                json.loads((config / "config.json").read_text()),
                {"auths": {"https://index.docker.io/v1/": {}}},
            )
        if command[3] == "login":
            self.assertEqual(kwargs["input"], b"synthetic-token\n")
            (config / "config.json").write_text("synthetic credential")
        elif command[3] == "pull":
            self.assertEqual(command[4:], ["--quiet", "--platform", "linux/arm64", IMAGE])
        elif command[3:5] == ["image", "inspect"]:
            self.assertEqual(command[5:], ["--format", "{{.Os}}/{{.Architecture}}", IMAGE])
            kwargs["stdout"].write(b"linux/arm64\n")
        else:
            self.fail("unexpected Docker operation")
        return subprocess.CompletedProcess(command, 0)

    def record(self):
        return json.loads((self.out / "result.json").read_text())

    def test_authenticated_pull_preserves_digest_and_erases_credentials(self):
        env = {
            "AETHRON_DOCKERHUB_USERNAME": "fixture",
            "AETHRON_DOCKERHUB_TOKEN": "synthetic-token",
        }
        with patch.dict(self.api.os.environ, env, clear=True):
            with patch.object(self.api.subprocess, "run", side_effect=self.docker):
                self.api.acquire(self.out)
        self.assertEqual(self.record()["state"], "acquired")
        self.assertEqual(self.record()["image"], IMAGE)
        self.assertEqual(self.record()["platform"], "linux/arm64")
        self.assertEqual(
            self.commands[0][3:],
            ["login", "docker.io", "--username", "fixture", "--password-stdin"],
        )
        self.assertNotIn("synthetic-token", json.dumps(self.commands) + json.dumps(self.record()))
        self.assertTrue(all(not path.exists() for path in self.configs))

    def test_anonymous_path_never_attempts_login(self):
        inherited = {"DOCKER_CONFIG": "/fixture/private", "DOCKER_AUTH_CONFIG": "fixture-private"}
        with patch.dict(self.api.os.environ, inherited, clear=True):
            with patch.object(self.api.subprocess, "run", side_effect=self.docker):
                self.api.acquire(self.out)
        self.assertEqual(self.commands[0][3], "pull")
        self.assertEqual(self.record()["authentication"], "anonymous")

    def test_partial_credentials_fail_without_docker(self):
        for env in (
            {"AETHRON_DOCKERHUB_USERNAME": "fixture"},
            {"AETHRON_DOCKERHUB_TOKEN": "synthetic-token"},
        ):
            out = self.out / str(len(env) + ("AETHRON_DOCKERHUB_TOKEN" in env))
            with patch.dict(self.api.os.environ, env, clear=True):
                with patch.object(
                    self.api.subprocess, "run", side_effect=AssertionError("docker_called")
                ):
                    with self.assertRaisesRegex(RuntimeError, "image_acquisition_failed"):
                        self.api.acquire(out)
            record = json.loads((out / "result.json").read_text())
            self.assertEqual(record["reason"], "invalid_credentials")

    def test_rate_limit_is_retained_without_output_or_credentials(self):
        def limited(command, **kwargs):
            self.assertEqual(command[3], "pull")
            kwargs["stdout"].write(b"toomanyrequests: pull rate limit; synthetic-token")
            return subprocess.CompletedProcess(command, 1)

        with patch.dict(self.api.os.environ, {}, clear=True):
            with patch.object(self.api.subprocess, "run", side_effect=limited):
                with self.assertRaises(RuntimeError):
                    self.api.acquire(self.out)
        self.assertEqual(self.record()["reason"], "rate_limited")
        self.assertEqual(self.record()["state"], "failed")
        self.assertNotIn("synthetic-token", (self.out / "result.json").read_text())

    def test_login_failure_does_not_retry_anonymously(self):
        def rejected(command, **kwargs):
            self.commands.append(command)
            self.configs.append(Path(command[2]))
            return subprocess.CompletedProcess(command, 1)

        env = {
            "AETHRON_DOCKERHUB_USERNAME": "fixture",
            "AETHRON_DOCKERHUB_TOKEN": "synthetic-token",
        }
        with patch.dict(self.api.os.environ, env, clear=True):
            with patch.object(self.api.subprocess, "run", side_effect=rejected):
                with self.assertRaises(RuntimeError):
                    self.api.acquire(self.out)
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.record()["stage"], "login")
        self.assertEqual(self.record()["state"], "failed")
        self.assertTrue(all(not path.exists() for path in self.configs))

    def test_wrong_platform_or_timeout_never_qualifies_acquisition(self):
        for mode in ("platform", "timeout", "missing"):
            out = self.out / mode

            def fail(command, mode=mode, **kwargs):
                if mode == "timeout":
                    raise subprocess.TimeoutExpired(command, 1)
                if mode == "missing":
                    raise FileNotFoundError("private host path")
                if command[3] == "image":
                    kwargs["stdout"].write(b"linux/amd64\n")
                return subprocess.CompletedProcess(command, 0)

            with patch.dict(self.api.os.environ, {}, clear=True):
                with patch.object(self.api.subprocess, "run", side_effect=fail):
                    with self.assertRaises(RuntimeError):
                        self.api.acquire(out)
            record = json.loads((out / "result.json").read_text())
            self.assertEqual(record["state"], "failed")
            self.assertNotIn("private host path", json.dumps(record))

    def test_existing_evidence_is_never_overwritten(self):
        self.out.mkdir()
        (self.out / "result.json").write_text("prior evidence")
        with patch.object(self.api.subprocess, "run", side_effect=AssertionError("docker_called")):
            with self.assertRaises(FileExistsError):
                self.api.acquire(self.out)
        self.assertEqual((self.out / "result.json").read_text(), "prior evidence")

    def test_inspection_timeout_does_not_reuse_pull_exit_code(self):
        def timeout(command, **kwargs):
            self.configs.append(Path(command[2]))
            if command[3] == "image":
                raise subprocess.TimeoutExpired(command, 15)
            return subprocess.CompletedProcess(command, 0)

        with patch.dict(self.api.os.environ, {}, clear=True):
            with patch.object(self.api.subprocess, "run", side_effect=timeout):
                with self.assertRaises(RuntimeError):
                    self.api.acquire(self.out)
        self.assertEqual(self.record()["stage"], "inspect")
        self.assertEqual(self.record()["reason"], "timeout")
        self.assertIsNone(self.record()["exit_code"])
        self.assertTrue(all(not path.exists() for path in self.configs))


if __name__ == "__main__":
    unittest.main()
