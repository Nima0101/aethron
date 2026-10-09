"""SIL only: explicit build provisioning and existing-state boot SDK checks.

Public synthetic key, no hardware/UDP/supervisor/continuous-availability claim.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

CONFIG = Path("/opt/aethron/telemetry-appliance.json")
RESULT = Path("/run/aethron-telemetry-check/result.json")
CHECKS = ("grant_preserved", "counter_advanced", "signed_packet_accepted", "duplicate_rejected")


def read_boot_result(path, boot_id):
    with path.open("rb") as stream:
        data = stream.read(4097)
    if len(data) > 4096:
        raise ValueError("telemetry_boot_result_oversize")
    result = json.loads(data)
    if (
        not isinstance(result, dict)
        or result.get("boot_id") != boot_id
        or result.get("kind") != "synthetic_direct_sdk"
        or result.get("prior_boot") not in ("initial", "same", "different")
        or any(result.get(key) is not True for key in CHECKS)
        or result.get("hardware_qualified") is not False
        or result.get("continuous_availability_qualified") is not False
    ):
        raise ValueError("telemetry_boot_result_incomplete")
    return result


def configuration(path):
    from aethron_edge.config import load_config
    from aethron_edge.runtime.updates import verify_configuration

    config = load_config(path)
    if config.runtime_mode != "appliance" or len(config.telemetry) != 1:
        raise ValueError("signed_sil_configuration_required")
    verify_configuration(config, path)
    item = config.telemetry[0]
    if item.clock_policy_file is None:
        raise ValueError("clock_policy_required")
    return item


def provision(path):
    """Image-construction only, as service UID; never called by the boot unit."""
    from aethron_edge.telemetry.signing import _private_parent

    item = configuration(path)
    policy_path = Path(item.clock_policy_file)
    _private_parent(policy_path)
    if policy_path.parent.is_symlink():
        raise ValueError("private_policy_parent_required")
    policy = {
        "version": 1,
        "system_id": item.system_id,
        "component_id": item.component_id,
        "key_hex": bytes(range(32)).hex(),
        "link_id": 7,
        "not_before_unix_ns": 1420070400000000000,
        "not_after_unix_ns": 4102444800000000000,
        "lease_ns": 60000000000,
        "drift_budget_ns": 1000000,
    }
    # No replacement, mode repair, recovery or automatic retry on a partial run.
    fd = os.open(item.clock_policy_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(policy, stream)
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "aethron_edge",
            "initialize-telemetry",
            "--config",
            str(path),
            "--name",
            item.name,
            "--replay-floor",
            "0",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )


def check(path):
    from aethron_edge.telemetry.boot_authority import issue_boot_trust
    from aethron_edge.telemetry.provisioning import current_boot_id, load_boot_policy
    from aethron_edge.telemetry.signing import SignedTelemetry, _identity
    from pymavlink.dialects.v20 import common

    item = configuration(path)
    policy = load_boot_policy(
        item.clock_policy_file, system=item.system_id, component=item.component_id
    )
    journal = Path(item.replay_file)
    _identity(journal)
    # mode=rw never creates missing replay state. Authority API validates schema/identity.
    with closing(sqlite3.connect(journal.as_uri() + "?mode=rw", uri=True)) as db:
        old = db.execute(
            "SELECT boot,issued,expires,floor FROM boot_authority WHERE id=1"
        ).fetchone()
        counter = db.execute("SELECT timestamp FROM replay WHERE id=1").fetchone()[0]
    boot = current_boot_id()
    grant = issue_boot_trust(journal, policy)
    if old[0] == boot and old[1:] != (grant.issued_ns, grant.valid_until_ns, grant.timestamp_floor):
        raise ValueError("grant_changed_on_restart")
    if issue_boot_trust(journal, policy) != grant:
        raise ValueError("grant_not_preserved")
    timestamp = max(counter, grant.timestamp_floor) + 1
    encoder = common.MAVLink(None, srcSystem=item.system_id, srcComponent=item.component_id)
    encoder.signing.secret_key = policy.key
    encoder.signing.sign_outgoing = True
    encoder.signing.link_id = policy.link_id
    encoder.signing.timestamp = timestamp
    packet = common.MAVLink_attitude_message(10, 0.1, 0.2, 0.3, 0, 0, 0).pack(encoder)
    receiver = SignedTelemetry(item.system_id, item.component_id, trust=grant, replay_path=journal)
    try:
        receiver.ingest(packet)
        accepted = bool(receiver.snapshot().samples)
        receiver.ingest(packet)
        duplicate_rejected = not receiver.snapshot().samples
    finally:
        receiver.close()
    with closing(sqlite3.connect(journal.as_uri() + "?mode=rw", uri=True)) as db:
        after = db.execute("SELECT timestamp FROM replay WHERE id=1").fetchone()[0]
    result = {
        "boot_id": boot,
        "kind": "synthetic_direct_sdk",
        "prior_boot": "initial" if old[0] is None else "same" if old[0] == boot else "different",
        "grant_preserved": True,
        "counter_advanced": after == timestamp and after > counter,
        "signed_packet_accepted": accepted,
        "duplicate_rejected": duplicate_rejected,
        "hardware_qualified": False,
        "continuous_availability_qualified": False,
    }
    if not all(result[key] for key in CHECKS):
        raise ValueError("telemetry_boot_check_failed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("provision", "check"))
    args = parser.parse_args()
    if args.command == "provision":
        provision(CONFIG)
    else:
        RESULT.unlink(missing_ok=True)
        result = check(CONFIG)
        temporary = RESULT.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, sort_keys=True) + "\n")
        temporary.replace(RESULT)
