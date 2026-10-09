"""Bounded regular-file access across inspection/open; no directory snapshot claim."""

import os
import stat
from contextlib import contextmanager


@contextmanager
def regular_reader(path, limit, *, metadata=None):
    before = path.lstat() if metadata is None else metadata
    if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= limit:
        raise ValueError("invalid_bundle")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not os.path.samestat(before, opened)
            or opened.st_size != before.st_size
            or not os.path.samestat(opened, path.lstat())
        ):
            raise ValueError("invalid_bundle")
        stream = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with stream as reader:
        yield reader, opened.st_size
