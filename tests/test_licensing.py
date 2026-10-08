"""Guard AETHRON's published community licence and dual-license disclosures."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GPL_ID = "GPL-3.0-only"


class LicensingPolicyTests(unittest.TestCase):
    def test_unmodified_gpl_v3_license_is_present(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(
            license_text.startswith("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007")
        )
        self.assertIn("END OF TERMS AND CONDITIONS", license_text)
        self.assertIn("How to Apply These Terms to Your New Programs", license_text)

    def test_root_package_metadata(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(pyproject, re.compile(r'^license = "GPL-3\.0-only"$', re.M))

    def test_web_package_metadata(self):
        package = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "web/package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(package["license"], GPL_ID)
        self.assertEqual(lock["packages"][""]["license"], GPL_ID)

    def test_sbom_identifies_the_application_not_third_party_as_gpl(self):
        source = (ROOT / "scripts/release.py").read_text(encoding="utf-8")
        self.assertIn('"licenses": [{"license": {"id": "GPL-3.0-only"}}]', source)
        self.assertIn('"licenses": [{"license": {"id": "CDLA-Permissive-1.0"}}]', source)

    def test_commercial_policy_is_separate_and_not_automatic(self):
        policy = (ROOT / "LICENSING.md").read_text(encoding="utf-8")
        commercial = (ROOT / "COMMERCIAL-LICENSING.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("commercial and business use", policy)
        self.assertIn("No commercial licence is automatically granted", policy)
        self.assertIn("signed agreement", commercial)
        self.assertIn("written permission", contributing)

    def test_frozen_legacy_and_third_party_licences_are_preserved(self):
        rules = json.loads((ROOT / "aethron/models/rules.json").read_text(encoding="utf-8"))
        self.assertEqual(rules["license"], "Apache-2.0")
        self.assertTrue((ROOT / "docs/models/YOLOX-LICENSE.txt").is_file())
        self.assertTrue((ROOT / "data/aot/LICENSE.txt").is_file())


if __name__ == "__main__":
    unittest.main()
