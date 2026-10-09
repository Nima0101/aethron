"""Opt-in test diagnostics only; never imported by installed product modules."""

import json
import sys
import threading
from contextlib import contextmanager
from unittest.mock import patch

MAX_LOG_BYTES = 65536
MAX_ROWS = 8
PREFIX = b"AETHRON_TIMING "
FIELDS = {
    "source_rejected": {"age_ns", "uncertainty_ns", "stamp_delta_ns", "receive_delta_ns"},
    "clock_rejected": {
        "sample_ns",
        "offset_delta_ns",
        "sample_error_ns",
        "grant_sample_error_ns",
        "budget_ns",
    },
}


def valid(row):
    if type(row) is not dict or type(row.get("event")) is not str:
        return False
    fields = FIELDS.get(row["event"])
    return (
        fields is not None
        and set(row) == fields | {"event"}
        and all(
            row[k] is None or (type(row[k]) is int and -(2**63 - 1) <= row[k] <= 2**63 - 1)
            for k in fields
        )
    )


def read_rows(stream):
    """Only whitelisted records from a bounded binary log tail may leave the test."""
    stream.seek(0, 2)
    start = max(0, stream.tell() - MAX_LOG_BYTES)
    stream.seek(start)
    lines = stream.read(MAX_LOG_BYTES).splitlines()
    if start:
        lines = lines[1:]  # Never interpret a truncated leading record.
    rows = []
    for line in lines:
        if not line.startswith(PREFIX) or len(line) > 1024:
            continue
        try:
            row = json.loads(line[len(PREFIX) :])
            if valid(row):
                rows.append(row)
                rows = rows[-MAX_ROWS:]
        except (ValueError, RecursionError):
            continue
    return rows


@contextmanager
def instrument(sink):
    from aethron_edge.sensors import ros_authority as authority
    from aethron_edge.sensors.ros2 import RosIngress

    sample, check, accept = authority._sample, authority.ClockGuard.check, RosIngress._accept
    local = threading.local()
    remaining = MAX_ROWS
    lock = threading.Lock()

    def emit(row):
        nonlocal remaining
        with lock:
            if remaining and valid(row):
                remaining -= 1
                try:
                    sink(row)
                except Exception:
                    pass  # A test-log failure must not change admission/revocation.

    def observed_sample(monotonic, realtime):
        result = sample(monotonic, realtime)
        local.sample = result
        return result

    def observed_check(self, **kwargs):
        closed = self.closed
        local.sample = None
        result = check(self, **kwargs)
        if not result and not closed:
            row = dict.fromkeys(FIELDS["clock_rejected"])
            row["event"] = "clock_rejected"
            if local.sample is not None:
                before, after, offset, error = local.sample
                row.update(
                    sample_ns=after - before,
                    offset_delta_ns=offset - self.grant.offset_ns,
                    sample_error_ns=error,
                    grant_sample_error_ns=self.grant.sample_error_ns,
                    budget_ns=self.manifest.clock_drift_budget_ns,
                )
            emit(row)
        return result

    def observed_accept(self, payload, stamp, now, format_digest=None):
        mapping, previous, receipt = self.mapping, self.last_stamp, self.last_receive
        result = accept(self, payload, stamp, now, format_digest)
        if getattr(result, "reason", None) == "clock_discontinuity":
            emit(
                {
                    "event": "source_rejected",
                    "age_ns": None if mapping is None else now - stamp - mapping.offset_ns,
                    "uncertainty_ns": None if mapping is None else mapping.uncertainty_ns,
                    "stamp_delta_ns": None if previous is None else stamp - previous,
                    "receive_delta_ns": None if receipt is None else now - receipt,
                }
            )
        return result

    with (
        patch.object(authority, "_sample", observed_sample),
        patch.object(authority.ClockGuard, "check", observed_check),
        patch.object(RosIngress, "_accept", observed_accept),
    ):
        yield


def write_row(row):
    print(PREFIX.decode() + json.dumps(row, sort_keys=True), file=sys.stderr, flush=True)


def child_environment(directory, environment):
    """Provision only the explicit test child; never install a global startup hook."""
    import os
    import shutil
    from pathlib import Path

    directory.mkdir()
    shutil.copyfile(Path(__file__), directory / "ros_timing_probe.py")
    (directory / "sitecustomize.py").write_text(
        "from ros_timing_probe import instrument, write_row\n"
        "_probe = instrument(write_row)\n_probe.__enter__()\n"
    )
    return dict(
        environment, PYTHONPATH=str(directory) + os.pathsep + environment.get("PYTHONPATH", "")
    )
