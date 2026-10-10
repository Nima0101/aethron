"""Small artifact-binding experiment; no hardware or cross-language speed claim."""

import hashlib
import json
import platform
import time
import tracemalloc
from pathlib import Path

from qualification.artifacts import verify
from qualification.tests.test_evidence import encoded, fixture


def main():
    inputs = [bytes([value]) * 1048576 for value in range(4)]
    digests = [hashlib.sha256(value).hexdigest() for value in inputs]
    supplied = dict(zip(digests, inputs))
    doc = fixture()
    for index, row in enumerate(doc["records"]):
        row["artifact_sha256"] = digests[index % 4]
    manifest = encoded(doc)
    samples = []
    for _ in range(10):
        start = time.perf_counter_ns()
        report = verify(manifest, supplied, now_ms=1050)
        samples.append(time.perf_counter_ns() - start)
        if not report["artifact_bytes_verified"] or report["physical_qualification_passed"]:
            raise RuntimeError("binding_measurement_failed")
    tracemalloc.start()
    verify(manifest, supplied, now_ms=1050)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    root = Path(__file__).parents[2]
    print(
        json.dumps(
            {
                "scope": "four_mib_production_artifact_binding",
                "python": platform.python_version(),
                "hash_backend_module": type(hashlib.sha256()).__module__,
                "four_mib_digests": digests,
                "verify_elapsed_ns": samples,
                "traced_peak_bytes_one_call": peak,
                "input_storage_excluded_from_tracing": True,
                "artifact_counts": report["artifact_counts"],
                "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                "source_sha256": {
                    name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                    for name in (
                        "qualification/artifacts.py",
                        "qualification/tests/test_evidence.py",
                        "qualification/technology/measure_binding.py",
                    )
                },
                "physical_qualification_passed": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
