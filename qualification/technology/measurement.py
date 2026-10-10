"""Check synthetic results and own tracing; not a process memory ceiling."""

import tracemalloc


def require_result(actual, expected, error):
    """Require a fixed synthetic result with exact container and scalar types."""
    if type(actual) is not type(expected):
        raise RuntimeError(error)
    if type(expected) is dict:
        if actual.keys() != expected.keys():
            raise RuntimeError(error)
        for key, value in expected.items():
            require_result(actual[key], value, error)
    elif type(expected) is list:
        if len(actual) != len(expected):
            raise RuntimeError(error)
        for value, wanted in zip(actual, expected):
            require_result(value, wanted, error)
    elif actual != expected:
        raise RuntimeError(error)


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
