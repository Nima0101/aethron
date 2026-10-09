"""Bounded offline recording I/O, independent of acquisition and geometry runtimes."""

import os
import stat
from contextlib import contextmanager
from pathlib import Path

from .replay import read_frames

MAX_RECORDING_BYTES = 64 * 1024 * 1024


@contextmanager
def regular_file(path, limit):
    # O_NONBLOCK prevents a substituted FIFO from blocking before fstat; reject
    # special files/symlinks before use. No device source is opened by replay.
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid_recording")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= limit:
            raise ValueError("invalid_recording")
        yield stream


def recording_frames(stream):
    """One pending raw record; finite software replay envelope, no wall-clock rebase."""
    first = None
    for index, frame in enumerate(read_frames(stream)):
        if first is None:
            first = frame.header.acquisition_ns
        if index >= 300 or frame.header.acquisition_ns - first > 30_000_000_000:
            raise ValueError("recording_limit")
        yield frame
    if first is None:
        raise ValueError("empty_recording")
