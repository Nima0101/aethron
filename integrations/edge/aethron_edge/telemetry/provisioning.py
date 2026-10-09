"""Private boot-bound telemetry credentials. SPDX-License-Identifier: GPL-3.0-only.

The local provisioner is trusted to supply the signing epoch/anchor. This loader
never infers it from packets, creates replay state, or renews expired authority.
"""

import os
import re
import stat
import time
from pathlib import Path

from ..config import strict_json
from .signing import SigningTrust

LIMIT = 2048
_FIELDS = frozenset(
    {
        "version",
        "boot_id",
        "system_id",
        "component_id",
        "key_hex",
        "link_id",
        "timestamp_floor",
        "issued_ns",
        "valid_until_ns",
    }
)
_BOOT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def current_boot_id():
    """Linux kernel boot identity, not an application session or persisted guess."""
    with Path("/proc/sys/kernel/random/boot_id").open("rb") as stream:
        value = stream.read(38).decode("ascii").strip()
    if not _BOOT.fullmatch(value):
        raise ValueError("invalid_boot_identity")
    return value


def _metadata(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_mode,
        info.st_uid,
        info.st_nlink,
    )


def _read_private(path):
    # Require POSIX enforcement rather than silently dropping security flags on
    # unsupported hosts. Pin the private parent and read/check one descriptor.
    path = Path(path).absolute()
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent = os.fstat(directory)
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError("invalid_private_directory")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1
                or not 1 <= before.st_size <= LIMIT
            ):
                raise ValueError("invalid_private_file")
            raw = os.read(fd, LIMIT + 1)
            if len(raw) != before.st_size or _metadata(before) != _metadata(os.fstat(fd)):
                raise ValueError("credential_changed")
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def load_trust(path, *, system, component):
    """Load existing authority for this boot and sender; no filesystem writes.

    Same-UID administrators/provisioners are the trust boundary. No claim of
    TPM-backed provenance, resistance to a compromised service UID, or secure
    memory zeroization. A missing kernel boot source refuses loading.
    """
    try:
        if any(type(x) is not int or not 1 <= x <= 255 for x in (system, component)):
            raise ValueError("invalid_sender")
        value = strict_json(_read_private(path), limit=LIMIT)
        if (
            type(value) is not dict
            or set(value) != _FIELDS
            or type(value["version"]) is not int
            or value["version"] != 1
            or type(value["system_id"]) is not int
            or value["system_id"] != system
            or type(value["component_id"]) is not int
            or value["component_id"] != component
            or type(value["boot_id"]) is not str
            or not _BOOT.fullmatch(value["boot_id"])
            or value["boot_id"] != current_boot_id()
            or type(value["key_hex"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", value["key_hex"])
        ):
            raise ValueError("invalid_credential_fields")
        trust = SigningTrust(
            bytes.fromhex(value["key_hex"]),
            value["link_id"],
            value["timestamp_floor"],
            value["issued_ns"],
            value["valid_until_ns"],
        )
        now = time.monotonic_ns()  # Reads/validation must not consume the remaining lease.
        if type(now) is not int or not trust.issued_ns <= now < trust.valid_until_ns:
            raise ValueError("invalid_credential_time")
        return trust
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        raise ValueError("invalid_telemetry_credential") from None


def load_boot_policy(path, *, system, component):
    """Read an explicit administrator clock policy; never provision or issue here.

    The private POSIX file has the same owner/mode/size rules as v1 credentials.
    UTC eligibility is checked by the issuer, after binding to the existing journal.
    """
    from .boot_authority import BootClockPolicy

    try:
        if any(type(x) is not int or not 1 <= x <= 255 for x in (system, component)):
            raise ValueError("invalid_sender")
        value = strict_json(_read_private(path), limit=LIMIT)
        fields = {
            "version",
            "system_id",
            "component_id",
            "key_hex",
            "link_id",
            "not_before_unix_ns",
            "not_after_unix_ns",
            "lease_ns",
            "drift_budget_ns",
        }
        if (
            type(value) is not dict
            or set(value) != fields
            or type(value["version"]) is not int
            or value["version"] != 1
            or type(value["system_id"]) is not int
            or value["system_id"] != system
            or type(value["component_id"]) is not int
            or value["component_id"] != component
            or type(value["key_hex"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", value["key_hex"])
        ):
            raise ValueError("invalid_policy_fields")
        return BootClockPolicy(
            bytes.fromhex(value["key_hex"]),
            system,
            component,
            value["link_id"],
            value["not_before_unix_ns"],
            value["not_after_unix_ns"],
            value["lease_ns"],
            value["drift_budget_ns"],
        )
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        raise ValueError("invalid_telemetry_clock_policy") from None
