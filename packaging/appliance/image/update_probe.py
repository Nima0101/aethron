"""Guest-local actual offline update transaction; no private signing key needed."""

import grp
import json
import os
from pathlib import Path

from aethron_edge.runtime.updates import UpdateStore


def run():
    key = Path("/etc/aethron/trust.pub")
    store = UpdateStore(Path("/var/lib/aethron-updates"), key)
    print(json.dumps({"stage": "stage_initial"}), flush=True)
    old = store.stage_update(Path("/opt/aethron"))
    print(json.dumps({"stage": "activate_initial"}), flush=True)
    store.activate(old)
    # An incomplete staging write must not change the active image.
    (store.root / "interrupted.pending").mkdir()
    assert store.recover()["version"] == 1
    print(json.dumps({"stage": "stage_second"}), flush=True)
    candidate = store.stage_update(Path("/opt/aethron-update-candidate"))
    print(json.dumps({"stage": "activate_second"}), flush=True)
    store.activate(candidate)
    assert store.recover()["version"] == 2
    try:
        store.activate(old)
    except ValueError:
        pass
    else:
        raise AssertionError("rollback accepted")
    # Root-owned slots readable/executable by the dedicated service account.
    group = grp.getgrnam("aethron").gr_gid
    for path in [store.root, *store.root.rglob("*")]:
        os.chown(path, 0, group)
        path.chmod(0o750 if path.is_dir() else (0o550 if path.stat().st_mode & 0o111 else 0o440))
    print(
        json.dumps(
            {
                "updated": True,
                "version": 2,
                "rollback_rejected": True,
                "interrupted_stage_preserved_active": True,
            }
        )
    )


if __name__ == "__main__":
    run()
