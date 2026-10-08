# Home camera hub operator guide — candidate

Provision the fixed hub once with authorized local camera streams, local credentials and compatible sensors. Leave its power/PoE and camera LAN connected. Power-on starts processing automatically; daily operation needs no phone app, monitor, laptop, WAN, cloud login or licensing heartbeat.

Read the local status indicator. UNKNOWN can mean an unavailable camera, stale timestamps, unsupported darkness or a fault. If it persists, ask the installer to check power, local networking, permissions and calibration. Do not expose the local API to the internet. Disable recording/upload unless separately authorized; temporary geometry must not become household identity history.

Cloud-only cameras without a permitted local stream are not supported by assumption. The common software boot test uses a Linux guest; exact camera/NVR/NAS/PoE hardware and zero-visible optics remain unqualified. Sensor wiring and power remain necessary after the setup tool is removed.
