"""Spawned acquisition workers need configuration, not HTTP schema construction."""

import subprocess
import sys
import unittest


class WorkerImports(unittest.TestCase):
    def test_cli_import_does_not_load_replay_or_http_schemas(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import aethron_edge.cli; "
                "assert 'aethron_edge.protocol' not in sys.modules; "
                "assert 'aethron_edge.contracts' not in sys.modules; "
                "assert 'fastapi' not in sys.modules",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_worker_import_does_not_load_api_schemas(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import aethron_edge.pipeline; "
                "assert 'aethron_edge.contracts' not in sys.modules; "
                "assert 'fastapi' not in sys.modules",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_principal_import_and_pickle_are_compatible(self):
        import pickle

        from aethron_edge.config import Credential
        from aethron_edge.contracts import Principal

        principal = Principal(name="reader", scopes=["observe"])
        # Protocol-0 GLOBAL refers to the original public module path. Existing
        # pickles from the old import location must still resolve that symbol.
        legacy = b"caethron_edge.contracts\nPrincipal\n."
        self.assertIs(pickle.loads(legacy), Principal)
        self.assertEqual(pickle.loads(pickle.dumps(principal)), principal)
        self.assertIs(Credential.model_fields["principal"].annotation, Principal)
