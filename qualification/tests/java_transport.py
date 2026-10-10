"""Optional real-Java transport controls; explicit classpath, no silent skips."""

import json
import os
import subprocess
import unittest


class JavaTransportTests(unittest.TestCase):
    def invoke(self, payload, *, stdout=subprocess.PIPE, jvm_options=()):
        return subprocess.run(
            [
                "java",
                "-Xint",
                "-XX:ActiveProcessorCount=1",
                "-XX:+UseSerialGC",
                "-Xmx64m",
                *jvm_options,
                "-cp",
                os.environ["QUALIFICATION_AUDIT_CLASSPATH"],
                "IngressProbe",
            ],
            input=payload,
            stdout=stdout,
            stderr=subprocess.PIPE,
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

    def test_output_failure_is_not_success_or_input_rejection(self):
        # This optional module runs on the Linux audit job; no silent skip.
        for payload in (b"7b7d\n", b"not_hex\n"):
            with self.subTest(payload=payload), open("/dev/full", "wb", buffering=0) as sink:
                result = self.invoke(payload, stdout=sink)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"probe_output_unavailable", result.stderr)

    def test_response_is_utf8_when_default_output_encoding_is_ascii(self):
        document = {"label": "\u00c5ngstr\u00f6m \U0001f6df"}
        payload = json.dumps(document, ensure_ascii=False).encode("utf-8").hex().encode() + b"\n"
        result = self.invoke(
            payload,
            jvm_options=(
                "-Dfile.encoding=US-ASCII",
                "-Dsun.stdout.encoding=US-ASCII",
                "-Dstdout.encoding=US-ASCII",
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout), {"accepted": True, "document": document})


if __name__ == "__main__":
    unittest.main()
