"""Small parser regressions; a stalled parser cannot stall the test runner."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = """
import json, sys
from scripts.markdown_links import local_destinations
try:
    print(json.dumps({'links': list(local_destinations(sys.stdin.read()))}))
except ValueError as error:
    print(json.dumps({'error': str(error)}))
"""


class MarkdownResources(unittest.TestCase):
    def parse(self, text):
        result = subprocess.run(
            [sys.executable, "-c", PROBE],
            input=text,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=3,
            check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_thirty_two_quotes_keep_the_destination(self):
        self.assertEqual(self.parse("> " * 32 + "[x](absent.md)\n"), {"links": ["absent.md"]})

    def test_quote_boundary_is_explicit(self):
        self.assertEqual(self.parse("> " * 63 + "[x](absent.md)\n"), {"links": ["absent.md"]})
        self.assertEqual(
            self.parse("> " * 64 + "[x](absent.md)\n"),
            {"error": "markdown_nesting_limit"},
        )

    def test_deep_link_label_is_rejected_explicitly(self):
        self.assertEqual(
            self.parse("[" * 256 + "[x](absent.md)" + "]" * 256),
            {"error": "markdown_nesting_limit"},
        )

    def test_excessive_quotes_fail_instead_of_omitting_links(self):
        self.assertEqual(
            self.parse("[first](first.md)\n\n" + "> " * 128 + "[x](absent.md)\n"),
            {"error": "markdown_nesting_limit"},
        )

    def test_nested_image_labels_fail_instead_of_exhausting_recursion(self):
        text = "[x](absent.md)"
        for _ in range(128):
            text = "![" + text + "](image.png)"
        self.assertEqual(self.parse(text), {"error": "markdown_nesting_limit"})

    def test_wide_emphasis_retains_link(self):
        self.assertEqual(
            self.parse("*a " * 256 + "[x](absent.md)" + " b*" * 256),
            {"links": ["absent.md"]},
        )

    def test_entities_and_percent_escapes_decode_exactly_once(self):
        self.assertEqual(
            self.parse("[x](a&amp;amp;b%2520c.md)"),
            {"links": ["a&amp;b%20c.md"]},
        )

    def test_image_and_label_links_keep_document_order(self):
        self.assertEqual(
            self.parse("[![x](image.png)](outer.md) ![[x](inner.md)](second.png)"),
            {"links": ["outer.md", "image.png", "second.png", "inner.md"]},
        )
