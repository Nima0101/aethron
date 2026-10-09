"""Guest-only ROS systemd lifecycle evidence; never a continuous-availability claim."""

import json
import subprocess
from pathlib import Path

RESULT = Path("/run/aethron-ros-check/result.json")
CONFIG = Path("/opt/aethron/ros-appliance.json")
UNIT = "aethron-ros-fixture.service"
CHECKS = (
    "processing_observed",
    "source_expiry_verified",
    "reconnect_cannot_revive",
    "explicit_restart_revalidated",
    "source_rewind_verified",
    "clock_restore_cannot_revive",
)


def read_boot_result(path, boot_id):
    with path.open("rb") as stream:
        data = stream.read(4097)
    if len(data) > 4096:
        raise ValueError("ros_boot_result_oversize")
    result = json.loads(data)
    if (
        not isinstance(result, dict)
        or result.get("boot_id") != boot_id
        or result.get("service_manager") != "systemd"
        or any(result.get(key) is not True for key in CHECKS)
        or result.get("hardware_qualified") is not False
        or result.get("continuous_availability_qualified") is not False
        or result.get("scene_state") != "UNKNOWN"
        or type(result.get("viewers")) is not int
        or result["viewers"] != 0
    ):
        raise ValueError("ros_boot_result_incomplete")
    return result


class SystemdFixture:
    """Fixed test-only guest unit, no caller-selected command or host service."""

    @staticmethod
    def command(*args):
        return subprocess.run(
            ["/usr/bin/systemctl", *args, UNIT],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()

    def start(self):
        self.command("start")

    def stop(self):
        self.command("stop")

    def poll(self):
        # A failed/auto-restarting incarnation must not masquerade as healthy.
        state = self.command("show", "--property=ActiveState", "--value")
        return None if state == "active" else 1


def main():
    from ros_lifecycle_probe import run_scenario

    RESULT.unlink(missing_ok=True)
    result = run_scenario(CONFIG, service=SystemdFixture())
    result.update(
        boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        service_manager="systemd",
    )
    temporary = RESULT.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, sort_keys=True) + "\n")
    temporary.replace(RESULT)


if __name__ == "__main__":
    main()
