"""CLI lifecycle: verified local processing starts before deferred HTTP imports."""

import signal

from .._startup_trace import mark
from .supervisor import ApplianceSupervisor


def run(config):
    """Own the runtime on the main thread after CLI configuration verification.

    HTTP loading may be slow or fail. Keep worker ownership and termination
    handling in this lightweight scope, including partial boot failures.
    """
    supervisor = ApplianceSupervisor()
    previous = {}
    stopping = False

    def terminate(signum, frame):
        if not stopping:
            raise SystemExit(128 + signum)

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, terminate)
        try:
            mark("runtime_boot_start")
            supervisor.boot(config)
            mark("runtime_boot_done")
            mark("http_import_start")
            from ..service.app import serve

            mark("http_import_done")
            serve(config, supervisor=supervisor)
        finally:
            stopping = True
            supervisor.shutdown()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
