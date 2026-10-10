"""Synthetic Markdown destinations; product children are intercepted."""

import unittest

from scripts import verify
from tests import test_verify_static as static_checks

CASES = (
    ('[guide](guide.md "Title")', ("guide.md",), False),
    ("[guide](<a guide.md>)", ("a guide.md",), False),
    ("[guide](a%20guide.md#section)", ("a guide.md",), False),
    ("[guide](guide(v1).md)", ("guide(v1).md",), False),
    ("[guide](guide.md?view=1#section)", ("guide.md",), False),
    ("[guide][ref]\n\n[ref]: guide.md", ("guide.md",), False),
    ("![image][ref]\n\n[ref]: absent.png", (), True),
    ("[guide][ref]\n\n[ref]: absent.md", (), True),
    ("[guide][]\n\n[guide]: absent.md", (), True),
    ("[guide]\n\n[guide]: absent.md", (), True),
    ("`[example](absent.md)`", (), False),
    ("```md\n[example](absent.md)\n```", (), False),
    ("\\[example](absent.md)", (), False),
    ("[mail](mailto:example@example.invalid)", (), False),
    ("[remote](https://example.invalid/) [anchor](#section)", (), False),
    ("[missing](absent.md)", (), True),
    ("[guide](a&amp;b.md)", ("a&b.md",), False),
    ("[guide](a%2520b.md)", ("a%20b.md",), False),
    ("[guide](a%23b.md)", ("a#b.md",), False),
    ("[guide](a\\(b\\).md)", ("a(b).md",), False),
)


class WorkingTreeLinks(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    def test_excessive_nesting_prevents_success_and_later_checks(self):
        with self.fixture("value = 1") as (output, calls):
            (verify.ROOT / "docs/sample.md").write_text(
                "> " * 64 + "[missing](absent.md)\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "^markdown_nesting_limit$"):
                verify.run()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_rendered_destinations_not_link_shaped_literals(self):
        for text, targets, missing in CASES:
            with self.subTest(text=text), self.fixture("value = 1") as (output, _):
                directory = verify.ROOT / "docs"
                (directory / "sample.md").write_text(text, encoding="utf-8")
                for target in targets:
                    (directory / target).write_text("synthetic", encoding="utf-8")
                if missing:
                    with self.assertRaises(AssertionError):
                        verify.run()
                    self.assertEqual(output.getvalue(), "")
                else:
                    verify.run()
