"""Bounded software-clock diagnostic; never issues authority or changes OS time."""

import argparse
import json
import time

from aethron_edge.sensors.ros_authority import _sample

BUDGET_NS = 1_000_000
MAX_SAMPLES = 1501
INTERVAL_SECONDS = 0.02


def check(
    *,
    samples=MAX_SAMPLES,
    monotonic=time.monotonic_ns,
    realtime=time.time_ns,
    sleep=time.sleep,
):
    if type(samples) is not int or not 2 <= samples <= MAX_SAMPLES:
        raise ValueError("invalid_sample_count")
    result = {
        "schema_version": 1,
        "kind": "software_clock_diagnostic",
        "qualified": False,
        "status": "within_budget",
        "budget_ns": BUDGET_NS,
        "samples": 0,
        "rejected_samples": 0,
        "baseline_sample_error_ns": None,
        "max_sample_error_ns": 0,
        "max_abs_offset_delta_ns": 0,
        "first_rejections": [],
    }
    anchor = last = None
    for index in range(samples):
        if index:
            sleep(INTERVAL_SECONDS)
        reason = delta = error = None
        try:
            before, after, offset, error = _sample(monotonic, realtime)
            if anchor is None:
                anchor = offset
                result["baseline_sample_error_ns"] = error
            delta = offset - anchor
            result["max_abs_offset_delta_ns"] = max(result["max_abs_offset_delta_ns"], abs(delta))
            result["max_sample_error_ns"] = max(result["max_sample_error_ns"], error)
            if last is not None and before < last:
                reason = "clock_rewind"
            elif abs(delta) + error > BUDGET_NS + result["baseline_sample_error_ns"]:
                reason = "clock_drift"
            last = after
        except (ValueError, TypeError, OverflowError):
            reason = "clock_sample_invalid"
        result["samples"] += 1
        if reason is not None:
            result["status"] = "rejected"
            result["rejected_samples"] += 1
            if len(result["first_rejections"]) < 8:
                result["first_rejections"].append(
                    {
                        "index": index,
                        "reason": reason,
                        "offset_delta_ns": delta,
                        "sample_error_ns": error,
                    }
                )
        if anchor is None:
            break  # A failed initial sample cannot silently acquire a later baseline.
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=MAX_SAMPLES)
    args = parser.parse_args()
    if not 2 <= args.samples <= MAX_SAMPLES:
        parser.error("samples must be between 2 and 1501")
    result = check(samples=args.samples)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "within_budget" else 1


if __name__ == "__main__":
    raise SystemExit(main())
