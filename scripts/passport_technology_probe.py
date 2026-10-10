"""Bounded local audit evidence; not a verifier, benchmark gate or qualification."""

import base64
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aethron.passports import _parse, pae, verify  # noqa: E402


def _comparison_response(raw):
    """Validate captured evidence, not the subprocess resource boundary."""
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise ValueError("comparison_response_size")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("comparison_duplicate_key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("comparison_nonfinite_number")

    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except RecursionError as error:
        raise ValueError("comparison_response_nesting") from error
    fields = {
        "node",
        "crypto_accepts",
        "hash_digest",
        "hash_1mib_ms",
        "duplicate_keys_collapsed",
        "float_lexemes_collapsed",
    }
    if type(result) is not dict or result.keys() != fields:
        raise ValueError("comparison_response_fields")
    accepts = result["crypto_accepts"]
    if (
        type(accepts) is not list
        or len(accepts) != 6
        or any(type(value) is not bool for value in accepts)
    ):
        raise ValueError("comparison_response_booleans")
    for field in ("duplicate_keys_collapsed", "float_lexemes_collapsed"):
        if result[field] is not True:
            raise ValueError("comparison_parser_observation")
    node = result["node"]
    if (
        type(node) is not str
        or len(node) > 128
        or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", node)
    ):
        raise ValueError("comparison_node_version")
    digest = result["hash_digest"]
    if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("comparison_digest")
    elapsed = result["hash_1mib_ms"]
    if type(elapsed) not in (int, float) or not 0 <= elapsed <= sys.float_info.max:
        raise ValueError("comparison_duration")
    return result


def main():
    if sys.flags.optimize:
        raise RuntimeError("optimized_probe_execution_forbidden")
    # Optional tools load only after the evidence-integrity gate.
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    cases = json.loads((ROOT / "examples/passports/vectors.json").read_bytes())["cases"]
    inputs, accepted, admissions = [], [], []
    for case in cases:
        envelope, policy = json.loads(case["envelope"]), json.loads(case["policy"])
        key = bytes.fromhex(policy["keys"][0]["public_key"])
        signature = base64.b64decode(envelope["signatures"][0]["sig"])
        message = pae(base64.b64decode(envelope["payload"]))
        inputs.append(
            {"publicKey": key.hex(), "signature": signature.hex(), "message": message.hex()}
        )
        try:
            Ed25519PublicKey.from_public_bytes(key).verify(signature, message)
            accepted.append(True)
        except InvalidSignature:
            accepted.append(False)
        result = verify(case["envelope"].encode(), case["policy"].encode(), **case["arguments"])
        assert (result.status, result.reason) == (case["status"], case["reason"])
        assert result.motion_authority is False and result.evidence_verified is False
        admissions.append(result.status)
    for raw in (b'{"version":0,"version":1}', b"1.0", b"1e0", b"[" * 9, b" " * 65537):
        try:
            _parse(raw)
        except ValueError:
            continue
        raise AssertionError("lexical/resource rejection lost")
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node is required for the explicit comparison; do not count a skip")
    compared = _comparison_response(
        subprocess.run(  # noqa: S603
            [node, "--v8-pool-size=1", str(ROOT / "scripts/passport_technology_probe.mjs")],
            input=json.dumps(inputs).encode(),
            capture_output=True,
            check=True,
            timeout=15,
        ).stdout
    )
    assert compared["crypto_accepts"] == accepted
    assert accepted == [True, True, True, True, False, True]
    blob = b"a" * 65536
    start = time.perf_counter()
    for _ in range(16):
        digest = hashlib.sha256(blob).hexdigest()
    hash_ms = (time.perf_counter() - start) * 1000
    assert compared["hash_digest"] == digest
    case = cases[0]
    envelope, policy = case["envelope"].encode(), case["policy"].encode()
    start = time.perf_counter()
    for _ in range(128):
        assert verify(envelope, policy, **case["arguments"]).status == "authenticated"
    verify_ms = (time.perf_counter() - start) * 1000 / 128
    tracemalloc.start()
    # Worst permitted input bytes, many tokens: syntax parses but schema rejects.
    adversarial = b"[" + b"0," * 32766 + b"0]"
    assert len(adversarial) <= 65536
    assert verify(adversarial, policy, **case["arguments"]).status == "rejected"
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        json.dumps(
            {
                "audit_policy_version": 2,
                "python": platform.python_version(),
                "fixture_sha256": hashlib.sha256(
                    (ROOT / "examples/passports/vectors.json").read_bytes()
                ).hexdigest(),
                "cases": len(cases),
                "crypto_accepts": accepted,
                "admissions": admissions,
                "python_lexical_rejections": 5,
                "python_hash_1mib_ms": hash_ms,
                "python_verify_mean_ms_128": verify_ms,
                "python_traced_peak_bytes": peak,
                "node_probe": compared,
                "limits": "Single local sample; no hard real-time, RSS, platform or qualification claim. Node primitive probe is not a full verifier.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
