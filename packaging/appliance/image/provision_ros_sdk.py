"""Install fixed Jazzy SDK paths into a dedicated Python 3.12 guest venv.

No download and no global Python modification. The pinned image supplies the SDK;
its libraries remain part of the image qualification, not the Python wheel.
"""

import os
import sys
import sysconfig
from pathlib import Path


def provision():
    if sys.prefix == sys.base_prefix or sys.version_info[:2] != (3, 12):
        raise ValueError("dedicated_python312_venv_required")
    sdk = Path("/opt/ros/jazzy")
    python_path = sdk / "lib/python3.12/site-packages"
    if not (python_path / "rclpy/__init__.py").is_file():
        raise ValueError("pinned_jazzy_sdk_missing")
    # Never turn caller-controlled PYTHONPATH into an executable .pth file.
    for path in (sdk, sdk.parent, python_path, *python_path.parents):
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise ValueError("untrusted_sdk_directory")
    site = Path(sysconfig.get_path("purelib"))
    if not site.is_relative_to(Path(sys.prefix)):
        raise ValueError("venv_site_required")
    target = site / "aethron-jazzy.pth"
    value = str(python_path) + "\n"
    if target.is_symlink() or (target.exists() and target.read_text() != value):
        raise ValueError("existing_sdk_path_conflict")
    target.write_text(value)
    target.chmod(0o644)
    environment = Path(sys.prefix) / "ros.env"
    if environment.is_symlink():
        raise ValueError("invalid_environment_file")
    environment.write_text(
        "AMENT_PREFIX_PATH=/opt/ros/jazzy\n"
        "LD_LIBRARY_PATH=/opt/ros/jazzy/lib:/opt/ros/jazzy/lib/aarch64-linux-gnu\n"
        "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST\n"
    )
    os.chmod(environment, 0o644)
    return target


if __name__ == "__main__":
    provision()
