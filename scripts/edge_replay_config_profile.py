"""Bounded decoder admission probe; optional candidates are never runtime dependencies."""

import hashlib
import json
import platform
import shutil
import statistics
import subprocess
import timeit
from pathlib import Path

import msgspec
import orjson


def unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def strict(data):
    return json.loads(data, object_pairs_hook=unique)


def main():
    duplicate = b'{"version":0,"version":1,"replay":"fixture.jsonl"}'
    escaped = b'{"version":0,"vers\\u0069on":1}'
    payload = b'{"version":1,"replay":"fixture.jsonl"}'
    decoders = {
        "stdlib_pairs": strict,
        "msgspec_C": msgspec.json.decode,
        "orjson_Rust_C": orjson.loads,
    }
    results = {}
    for name, decode in decoders.items():
        decisions = []
        for data in (duplicate, escaped):
            try:
                decode(data)
            except ValueError:
                decisions.append("reject")
            else:
                decisions.append("accept")
        if decode(payload) != {"version": 1, "replay": "fixture.jsonl"}:
            raise RuntimeError("valid configuration parity failure")
        if name == "stdlib_pairs" and decisions != ["reject", "reject"]:
            raise RuntimeError("duplicate rejection failure")
        samples = timeit.repeat(lambda decode=decode: decode(payload), number=2000, repeat=3)
        results[name] = {
            "duplicate_admission": decisions,
            "median_us_per_decode": statistics.median(samples) * 500,
        }
    # A semantics-preserving native-codec adapter needs duplicate-preserving parsing too.
    for name, decode in list(decoders.items())[1:]:

        def guarded(decode=decode):
            strict(payload)
            return decode(payload)

        samples = timeit.repeat(guarded, number=2000, repeat=3)
        results[name]["stdlib_duplicate_guard_plus_codec_us"] = statistics.median(samples) * 500
    node = shutil.which("node")
    if node:
        code = "const fs=require('node:fs'); const xs=JSON.parse(fs.readFileSync(0,'utf8')); console.log(JSON.stringify(xs.map(x=>{try{return JSON.parse(x).version===1?'accept':'reject'}catch{return 'reject'}})));"
        run = subprocess.run(
            [node, "-e", code],
            input=json.dumps([duplicate.decode(), escaped.decode()]),
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        )
        results["node_ECMAScript"] = {
            "duplicate_admission": json.loads(run.stdout),
            "version": subprocess.check_output([node, "--version"], text=True, timeout=5).strip(),
        }
    paths = [
        Path("scripts/edge_replay_config_profile.py"),
        Path("integrations/edge/requirements-json-probe.lock"),
        Path("integrations/edge/aethron_edge/cli.py"),
        Path("tests/integration/test_replay_config.py"),
    ]
    report = {
        "audit_policy_version": 2,
        "scope": "P1.1 CLI configuration decoder only",
        "qualified": False,
        "python": platform.python_version(),
        "msgspec": msgspec.__version__,
        "orjson": orjson.__version__,
        "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
