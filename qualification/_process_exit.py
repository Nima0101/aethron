"""Preserve failed command status when report or diagnostic delivery fails."""

import sys


def failure(diagnostic):
    """Attempt one fixed diagnostic; a failed endpoint cannot change status 2."""
    stream = sys.stderr
    if stream is None:
        # print(file=None) would redirect diagnostics into the report stream.
        return 2
    try:
        print(diagnostic, file=stream, flush=True)
    except (OSError, ValueError):
        # Includes writes to a closed caller-owned text stream. Do not retry,
        # echo the exception or redirect the diagnostic into the report stream.
        return 2
    return 2


def _close(stream):
    if stream is None:
        return
    try:
        stream.close()
    except (OSError, ValueError):
        # The command has already failed; still finalize its other stream.
        return


def finish(status):
    """Close process-owned output after exit 2; leave library streams alone."""
    if status == 2:
        _close(sys.stdout)
        _close(sys.stderr)
    return status
