"""Bounded local status, without imagery, geometry, identities or credentials."""

import json
import os
from pathlib import Path


def publish_status(path: Path, value: dict):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(data) > 4096:
        raise ValueError("status_limit")
    temporary = path.with_suffix(".pending")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
