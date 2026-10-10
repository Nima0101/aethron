"""Finalize failed module invocations without retrying broken stdout at exit."""

import sys


def finish(status):
    """Close process-owned stdout after exit 2; leave library main() streams alone."""
    if status == 2:
        try:
            sys.stdout.close()
        except OSError:
            # The command already failed and emitted its fixed diagnostic.
            return 2
    return status
