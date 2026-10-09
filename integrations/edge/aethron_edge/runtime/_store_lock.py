"""Nonblocking local-store mutation lock; never unlink a possibly locked inode."""

import errno
import os
import stat
from contextlib import contextmanager


@contextmanager
def exclusive_store(root):
    path = root / ".mutation.lock"
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        if path.is_symlink():
            raise ValueError("invalid_update_lock")
        fd = os.open(path, flags, 0o600)
    except OSError:
        raise ValueError("invalid_update_lock") from None
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not os.path.samestat(metadata, path.lstat())
        ):
            raise ValueError("invalid_update_lock")
        try:
            if os.name == "nt":
                import msvcrt

                # The descriptor starts at zero; locking beyond EOF is supported.
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise ValueError("update_store_busy") from None
            raise ValueError("update_lock_unavailable") from None
        yield
    finally:
        # Closing releases the OS lock, including on process termination. The
        # empty lock file persists across reset/restart; no PID/age-based bypass.
        os.close(fd)
