"""Own one synchronous Python-allocation trace; not a process memory ceiling."""

import tracemalloc


def require_untraced():
    if tracemalloc.is_tracing():
        raise RuntimeError("audit_tracing_already_active")


def peak_bytes(function, *args, **kwargs):
    """Call once, sample the peak, and release only this measurement's trace."""
    require_untraced()
    tracemalloc.start()
    try:
        function(*args, **kwargs)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
