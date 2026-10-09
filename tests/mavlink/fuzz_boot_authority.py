"""Seeded offline authority state campaign; synthetic keys/clocks, no hardware."""

import json
import random
import tempfile
import time
from pathlib import Path

from aethron_edge.telemetry.boot_authority import (
    MAVLINK_EPOCH_NS,
    BootClockPolicy,
    issue_boot_trust,
    provision_boot_authority,
)
from aethron_edge.telemetry.signing import SigningTrust, provision_replay


def issue(path, policy, mono, wall, boot):
    return issue_boot_trust(
        path, policy, monotonic=lambda: mono, realtime=lambda: wall, boot_id=lambda: boot
    )


def main():
    seed = 16034
    rng = random.Random(seed)
    started = time.monotonic()
    count = 0
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "replay.db"
        while time.monotonic() - started < 60 or count < 2000:
            mono = rng.randrange(1_000_000, 1_000_000_000)
            wall = MAVLINK_EPOCH_NS + 100_000_000_000
            lease = rng.randrange(100_000, 2_000_000_000)
            policy = BootClockPolicy(
                bytes(range(32)),
                1,
                1,
                7,
                wall - 1_000_000_000,
                wall + 300_000_000_000,
                lease,
                1_000_000,
            )
            provision_replay(path, SigningTrust(policy.key, 7, 0, 1, 2), system=1, component=1)
            provision_boot_authority(path, policy)
            boot = "aeeeeeee-1111-4111-8111-111111111111"

            grant = issue(path, policy, mono, wall, boot)
            forward = rng.randrange(1, lease)
            mono += forward
            wall += forward
            if issue(path, policy, mono, wall, boot) != grant:
                raise AssertionError("unexpected_renewal")
            rollback = rng.randrange(1, forward + 1)
            mono -= rollback
            wall -= rollback
            try:
                issue(path, policy, mono, wall, boot)
            except ValueError:
                pass
            else:
                raise AssertionError("rollback_accepted")
            mono += rollback
            wall += rollback
            try:
                issue(path, policy, mono, wall, boot)
            except ValueError:
                pass
            else:
                raise AssertionError("revoked_grant_revived")
            boot = "beeeeeee-1111-4111-8111-111111111111"
            mono = 100
            wall += 1_000_000
            successor = issue(path, policy, mono, wall, boot)
            if not successor.boot_bound or successor.issued_ns != mono:
                raise AssertionError("invalid_reboot_anchor")
            path.unlink()
            count += 1
    print(
        json.dumps(
            {
                "seed": seed,
                "cases": count,
                "seconds": time.monotonic() - started,
                "unexpected_acceptances": 0,
                "hardware_qualified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
