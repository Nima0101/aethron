"""Package verification must install locally despite inherited pip settings."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests

from scripts import package_check


class PackageInstallerEnvironment(unittest.TestCase):
    def test_environment_preserves_build_context_and_parent(self):
        parent = {
            "PATH": "selected-build-tools",
            "CC": "selected-compiler",
            "SOURCE_DATE_EPOCH": "unselected-epoch",
            "PYTHONPATH": "unselected-imports",
            "PYTHONHOME": "unselected-interpreter",
            "PIP_TARGET": "unselected-install",
            "pip_prefix": "unselected-prefix",
        }
        with patch.dict(os.environ, parent, clear=True):
            env = package_check.packaging_environment()
            self.assertEqual(dict(os.environ), parent)
        self.assertEqual(env["PATH"], parent["PATH"])
        self.assertEqual(env["CC"], parent["CC"])
        self.assertEqual(env["SOURCE_DATE_EPOCH"], "1767225600")
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        for key in ("PYTHONPATH", "PYTHONHOME", "PIP_TARGET", "pip_prefix"):
            self.assertNotIn(key, env)

    def test_core_install_ignores_parent_target_and_config(self):
        for setting in ("PIP_TARGET", "PIP_CONFIG_FILE"):
            with self.subTest(setting=setting), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / "redirected-install"
                config = root / "pip.ini"
                config.write_text(f"[install]\ntarget = {target}\n", encoding="utf-8")
                value = str(target if setting == "PIP_TARGET" else config)
                with (
                    patch.dict(os.environ, {setting: value}),
                    core_tests.CorePackageReport().fixture(real_install=True),
                ):
                    try:
                        package_check.run()
                    except subprocess.CalledProcessError:
                        self.fail("inherited installer settings broke the local core install")
                    self.assertEqual(os.environ[setting], value)
                self.assertFalse(target.exists(), "installer wrote outside its consumer venv")

    def test_edge_install_ignores_parent_target_and_config(self):
        for setting in ("PIP_TARGET", "PIP_CONFIG_FILE"):
            with self.subTest(setting=setting), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / "redirected-install"
                config = root / "pip.ini"
                config.write_text(f"[install]\ntarget = {target}\n", encoding="utf-8")
                value = str(target if setting == "PIP_TARGET" else config)
                with patch.dict(os.environ, {setting: value}):
                    try:
                        edge_tests.PackageInputEvidence().probe(real_install=True)
                    except subprocess.CalledProcessError:
                        self.fail("inherited installer settings broke the local edge install")
                    self.assertEqual(os.environ[setting], value)
                self.assertFalse(target.exists(), "installer wrote outside its consumer venv")

    def test_edge_children_share_explicit_installer_configuration(self):
        # No network requests: the harness models builds and installed consumers.
        inherited = {
            "PIP_FIND_LINKS": "https://invalid.example/wheels",
            "PIP_EXTRA_INDEX_URL": "https://invalid.example/simple",
            "PIP_REQUIREMENT": "unrequested-requirements.txt",
            "PIP_CONSTRAINT": "unrequested-constraints.txt",
            "PIP_PREFIX": "unrequested-prefix",
            "PIP_USER": "1",
            "PIP_DRY_RUN": "1",
            "PIP_PYTHON": "unrequested-python",
            "PIP_CONFIG_FILE": "unrequested-pip.ini",
            "pip_target": "case-insensitive-setting",
        }
        calls = []

        def check_child(args, kwargs):
            calls.append(args)
            settings = {k: v for k, v in kwargs["env"].items() if k.upper().startswith("PIP_")}
            self.assertTrue(
                settings == {"PIP_CONFIG_FILE": os.devnull, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
                "unexpected installer configuration in child environment",
            )

        with patch.dict(os.environ, inherited):
            edge_tests.PackageInputEvidence().probe(vision=True, on_process=check_child)
            self.assertTrue(all(os.environ[k] == v for k, v in inherited.items()))
        self.assertTrue(any("build" in args for args in calls))
        self.assertTrue(any("install" in args for args in calls))
        self.assertTrue(any("--installed-edge-payload" in args for args in calls))
