"""Opt-in local startup timings; fixed vocabulary, no caller data or retry loop."""

import os
import time

_ENABLED = os.environ.get("AETHRON_STARTUP_TRACE") == "1"
_STAGES = frozenset(
    {
        "process_entry",
        "cli_ready",
        "config_import_start",
        "config_import_done",
        "config_load_done",
        "verification_start",
        "bundle_signature_start",
        "bundle_signature_done",
        "bundle_hashes_done",
        "bundle_inventory_done",
        "verification_done",
        "runtime_import_start",
        "runtime_import_done",
        "runtime_boot_start",
        "runtime_boot_done",
        "http_import_start",
        "http_import_done",
    }
)
_emitted = set()


def mark(stage):
    if not _ENABLED or stage not in _STAGES or stage in _emitted:
        return
    _emitted.add(stage)
    try:
        os.write(2, f"AETHRON_STARTUP {stage} {time.monotonic_ns()}\n".encode("ascii"))
    except OSError:
        pass  # A diagnostic sink cannot replace the actual startup outcome.
