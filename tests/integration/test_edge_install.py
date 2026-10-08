"""Installed consumers must not accidentally import the checkout."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class InstalledEdge(unittest.TestCase):
    def test_installed_replay_without_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            env = dict(os.environ, SOURCE_DATE_EPOCH="1767225600")
            env.pop("PYTHONPATH", None)
            for project in (ROOT, ROOT / "integrations/edge"):
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "build",
                        "--no-isolation",
                        "--wheel",
                        "--outdir",
                        str(temp / "wheels"),
                        str(project),
                    ],
                    env=env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
            subprocess.run([sys.executable, "-m", "venv", str(temp / "consumer")], check=True)
            python = temp / "consumer" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--find-links",
                    str(temp / "wheels"),
                    "--find-links",
                    str(ROOT / "build/ecosystem-phase1/wheelhouse"),
                    "aethron-edge==0.1.0",
                ],
                cwd=temp,
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            config = temp / "replay.json"
            config.write_text(
                json.dumps({"version": 1, "replay": str(ROOT / "examples/temporal-blackout.jsonl")})
            )

            def invoke(command):
                return subprocess.run(
                    [str(python), "-I", "-m", "aethron_edge", command, "--config", str(config)],
                    cwd=temp,
                    env=env,
                    check=True,
                    text=True,
                    capture_output=True,
                )

            doctor = json.loads(invoke("doctor").stdout)
            self.assertEqual(doctor["core_version"], "0.2.0")
            self.assertFalse(doctor["hardware_probed"])
            self.assertFalse(doctor["qualified"])
            report = json.loads(invoke("replay").stdout)
            self.assertEqual(report["frame_count"], 24)
            self.assertEqual(
                report["results"][-1]["tracks"][0]["sources"], ["depth", "lwir", "radar"]
            )
            self.assertEqual(report["runtime_mode"], "replay")


if __name__ == "__main__":
    unittest.main()
