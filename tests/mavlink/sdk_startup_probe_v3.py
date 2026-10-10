"""Isolated installed-package characterization; no sockets or actuation.

Run on Linux with -I and installed core/edge wheels plus the optional SDK lock.
The blocked mode simulates an unavailable fastcrc import in this process only.
Timings are incremental wall observations, not cold-machine startup or WCET.
"""

import resource
import sys
import time


class BlockFastcrc:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "fastcrc" or fullname.startswith("fastcrc."):
            raise ImportError("synthetic_fastcrc_unavailable")
        return None


def probe(mode):
    if sys.platform != "linux" or mode not in ("installed", "blocked") or not sys.flags.isolated:
        raise ValueError("isolated_probe_mode_required")
    if any(name.startswith(("aethron_edge", "pymavlink", "fastcrc")) for name in sys.modules):
        raise ValueError("fresh_interpreter_required")
    blocker = BlockFastcrc()
    if mode == "blocked":
        sys.meta_path.insert(0, blocker)
    sources = []
    try:
        start = time.monotonic_ns()
        from aethron_edge.telemetry import mavlink

        imported = time.monotonic_ns()
        first = mavlink.PassiveTelemetry(1, 1, clock=lambda: 1_000_000_000)
        constructed = time.monotonic_ns()
        sources.append(first)
        second = mavlink.PassiveTelemetry(1, 1, clock=lambda: 1_000_000_000)
        repeated = time.monotonic_ns()
        sources.append(second)
        phase_ns = {
            "adapter_import": imported - start,
            "first_constructor": constructed - imported,
            "second_constructor": repeated - constructed,
        }
        if any(type(value) is not int or value < 0 for value in phase_ns.values()):
            raise ValueError("invalid_probe_duration")
        peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        initial_state = first.snapshot().state
        # Fixed synthetic packets generated once by the pinned SDK, independent
        # of the backend selected by this process. No transport or live feed.
        attitude = bytes.fromhex(
            "fd1c00000001011e00000a000000cdcccc3dcdcc4c3e9a99993ecdcccc3e0000003f9a99193f83ce"
        )
        position = bytes.fromhex(
            "fd1c00000101012000000a0000000000803f0000004000004040000080400000a0400000c04085a1"
        )
        first.ingest(attitude)
        first.ingest(position)
        messages = [sample.message for sample in first.snapshot().samples]
        first.ingest(position[:-1] + bytes([position[-1] ^ 1]))
        corrupt = first.snapshot()
        first.close()
        closed_reason = first.snapshot().reason

        # Hashing/metadata collection are outside all three timing intervals and
        # the RSS sample. Paths and arbitrary process modules are not exported.
        import hashlib
        from importlib.metadata import version
        from pathlib import Path

        prefix = Path(sys.prefix).resolve()
        module_sha256 = {}
        for name, module in tuple(sys.modules.items()):
            if name == mavlink.__name__ or name.startswith(("pymavlink", "fastcrc")):
                filename = getattr(module, "__file__", None)
                if filename is not None:
                    path = Path(filename).resolve()
                    if not path.is_relative_to(prefix):
                        raise ValueError("module_outside_installed_environment")
                    module_sha256[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        common = sys.modules["pymavlink.dialects.v20.common"]
        return {
            "schema_version": 1,
            "mode": mode,
            "isolated": bool(sys.flags.isolated),
            "python": sys.version.split()[0],
            "phase_ns": phase_ns,
            "peak_rss_kib": peak_rss_kib,
            "crc_backend": common.x25crc.__name__,
            "pymavlink_version": version("pymavlink"),
            "fastcrc_loaded": "fastcrc.fastcrc" in sys.modules,
            "lxml_loaded": any(name == "lxml" or name.startswith("lxml.") for name in sys.modules),
            "module_sha256": module_sha256,
            "initial_state": initial_state,
            "messages": messages,
            "corrupt_state": corrupt.state,
            "corrupt_reason": corrupt.reason,
            "corrupt_samples": len(corrupt.samples),
            "perception_eligible": corrupt.perception_eligible,
            "closed_reason": closed_reason,
        }
    finally:
        for source in sources:
            source.close()
        if mode == "blocked":
            sys.meta_path.remove(blocker)


if __name__ == "__main__":
    result = probe(sys.argv[1] if len(sys.argv) == 2 else "")
    import json

    print(json.dumps(result, sort_keys=True))
