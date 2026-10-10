"""Optional real-Java transport controls; explicit classpath, no silent skips."""

import json
import os
import subprocess
import unittest


class JavaTransportTests(unittest.TestCase):
    def invoke(self, payload):
        return subprocess.run(
            [
                "java",
                "-Xint",
                "-XX:ActiveProcessorCount=1",
                "-XX:+UseSerialGC",
                "-Xmx64m",
                "-cp",
                os.environ["QUALIFICATION_AUDIT_CLASSPATH"],
                "IngressProbe",
            ],
            input=payload,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def rows(self, payload):
        result = self.invoke(payload)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(result.stderr, b"")
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_trailing_empty_requests_remain_rejected_rows(self):
        self.assertEqual(
            self.rows(b"7b7d\n\n\n"),
            [{"accepted": True, "document": {}}, {"accepted": False}, {"accepted": False}],
        )

    def test_empty_rows_count_toward_batch_limit_before_output(self):
        for payload in (b"\n" * 257, b"7b7d\n" + b"\n" * 256):
            with self.subTest(bytes=len(payload)):
                result = self.invoke(payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertIn(b"java.lang.IllegalArgumentException", result.stderr)

    def test_exact_row_limit_retains_all_empty_requests(self):
        self.assertEqual(self.rows(b"\n" * 256), [{"accepted": False}] * 256)

    def test_terminal_newline_does_not_add_a_request(self):
        expected = [{"accepted": True, "document": {}}] * 256
        for payload in (b"7b7d\n" * 256, (b"7b7d\n" * 256)[:-1]):
            with self.subTest(terminated=payload.endswith(b"\n")):
                self.assertEqual(self.rows(payload), expected)

    def test_empty_transport_has_no_requests(self):
        self.assertEqual(self.rows(b""), [])

    def test_bad_hex_row_keeps_following_valid_row(self):
        self.assertEqual(
            self.rows(b"not_hex\n7b7d\n"),
            [{"accepted": False}, {"accepted": True, "document": {}}],
        )


if __name__ == "__main__":
    unittest.main()
