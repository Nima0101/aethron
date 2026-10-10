"""Small artifact-binding experiment; no hardware or cross-language speed claim."""

import hashlib
import json
import platform
import time
from pathlib import Path

from qualification.artifacts import verify
from qualification.technology import source_snapshot
from qualification.technology.measurement import peak_bytes, require_untraced
from qualification.tests.test_evidence import encoded, fixture


def _require_report(actual, expected):
    """Check this fixed synthetic result, including scalar and container types."""
    if type(actual) is not type(expected):
        raise RuntimeError("binding_measurement_failed")
    if type(expected) is dict:
        if actual.keys() != expected.keys():
            raise RuntimeError("binding_measurement_failed")
        for key, value in expected.items():
            _require_report(actual[key], value)
    elif type(expected) is list:
        if len(actual) != len(expected):
            raise RuntimeError("binding_measurement_failed")
        for value, wanted in zip(actual, expected):
            _require_report(value, wanted)
    elif actual != expected:
        raise RuntimeError("binding_measurement_failed")


def main():
    require_untraced()
    root = Path(__file__).parents[2]
    sources = source_snapshot.capture(
        root,
        (
            "qualification/artifacts.py",
            "qualification/evidence.py",
            "aethron/_json_bounds.py",
            "qualification/tests/test_evidence.py",
            "qualification/technology/measure_binding.py",
            "qualification/technology/measurement.py",
            "qualification/technology/source_snapshot.py",
        ),
    )
    inputs = [bytes([value]) * 1048576 for value in range(4)]
    digests = [hashlib.sha256(value).hexdigest() for value in inputs]
    supplied = dict(zip(digests, inputs))
    doc = fixture()
    for index, row in enumerate(doc["records"]):
        row["artifact_sha256"] = digests[index % 4]
    manifest = encoded(doc)
    expected = {
        "version": 1,
        "declaration": {
            "version": 1,
            "input_sha256": hashlib.sha256(manifest).hexdigest(),
            "declaration_checks_passed": True,
            "sensor_count": 2,
            "record_count": 6,
            "evidence_counts": {"synthetic": 6, "recorded": 0, "external_unverified": 0},
            "findings": [],
            "artifacts_verified": False,
            "physical_qualification_passed": False,
            "physical_status": "blocked_external_evidence_and_review",
        },
        "artifact_counts": {
            "referenced": 4,
            "supplied": 4,
            "matched": 4,
            "missing": 0,
            "mismatched": 0,
            "unreferenced": 0,
            "supplied_bytes": 4194304,
        },
        "artifact_findings": [],
        "artifact_bytes_verified": True,
        "software_checks_passed": True,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
    }
    samples = []
    for _ in range(10):
        start = time.perf_counter_ns()
        report = verify(manifest, supplied, now_ms=1050)
        samples.append(time.perf_counter_ns() - start)
        _require_report(report, expected)
    traced_report = None

    def traced_verify():
        nonlocal traced_report
        traced_report = verify(manifest, supplied, now_ms=1050)

    peak = peak_bytes(traced_verify)
    _require_report(traced_report, expected)
    source_snapshot.verify(root, sources)
    print(
        json.dumps(
            {
                "scope": "four_mib_production_artifact_binding",
                "audit_policy_version": 3,
                "python": platform.python_version(),
                "hash_backend_module": type(hashlib.sha256()).__module__,
                "four_mib_digests": digests,
                "verify_elapsed_ns": samples,
                "traced_peak_bytes_one_call": peak,
                "input_storage_excluded_from_tracing": True,
                "result_validation_excluded_from_measurements": True,
                "all_measured_results_checked": True,
                "artifact_counts": report["artifact_counts"],
                "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                "source_sha256": sources,
                "source_observation": "equal_before_and_after_workload",
                "physical_qualification_passed": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
