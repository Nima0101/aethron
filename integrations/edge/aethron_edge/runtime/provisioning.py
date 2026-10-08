"""Provisioning helper: local credentials have no online activation dependency."""

import os
import secrets
from pathlib import Path


def create_token(path: Path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(secrets.token_hex(32) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def reset_credentials(paths: list[Path]):
    for path in paths:
        if path.is_symlink():
            raise ValueError("invalid_credentials")
        path.unlink(missing_ok=True)
