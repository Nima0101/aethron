# Drone compatibility — observation/integration blueprint

A camera attached to a drone and detection of an external UAV are distinct capabilities. A supported video transport does not qualify small-UAV detection. AETHRON's current aircraft excerpt contains fixed-wing aircraft and a failed detector result, not a qualified drone model.

## Upstream pathways, not AETHRON support claims

| Stack | Candidate version / access | Required adapter and limits |
|---|---|---|
| PX4 | v1.16 docs; uXRCE-DDS Agent v2.4.3; Ubuntu 22.04/ROS 2 Humble | Match `px4_msgs` to firmware, board DDS topics and simulator; client v2.x/Agent v3.x incompatible [S10](SOURCES.md#s10), [S11](SOURCES.md#s11) |
| ArduPilot | companion MAVLink interface; exact firmware release selected at lane kickoff | Separate passive/read-only telemetry and camera stream; pin firmware, dialect and simulator commit before tests [S12](SOURCES.md#s12) |
| MAVLink/MAVSDK | camera protocol v2; MAVSDK v4.0.5 upstream observed | Stream discovery/telemetry is not pixel transport or frame sync; versioned bindings and camera URI decoder required [S13](SOURCES.md#s13), [S14](SOURCES.md#s14) |
| ROS 2 camera | Image + CameraInfo; Humble/PX4 lane and separate Jazzy generic-camera lane | Correct optical frames/encoding/stride, transform, QoS, clock mapping; no inference from `frame_id` string alone [S32](SOURCES.md#s32), [S33](SOURCES.md#s33) |
| DJI Mobile SDK | Android V5.18.0 observed; exact product/controller matrix required | Authorized decoded-frame callback/stream access where exposed. Public list includes Mini 3/3 Pro/4 Pro, Mavic 3 Enterprise and Matrice variants; not every DJI drone [S15](SOURCES.md#s15), [S16](SOURCES.md#s16) |
| DJI Payload/Onboard/Cloud | separate vendor products, not interchangeable universal APIs | PSDK documentation rendered empty in research; connector/power/activation/firmware/terms remain a gate. OSDK or Cloud API cannot be assumed to expose all camera frames [S17](SOURCES.md#s17) |
| Parrot | Olympe 8.4.0 Linux + Sphinx simulation | Documented ANAFI-family streamed frames/metadata; prebuilt x86_64 restriction, ARM source-build evidence needed; no assumption all Parrot models share features [S18](SOURCES.md#s18) |
| Other commercial/FPV | documented RTSP/RTP/UVC/CSI payload or approved vendor export | Proprietary encrypted radio/app video unavailable without authorized API; HDMI capture is a separately tested delayed path |

PX4/ArduPilot/MAVSDK source licensing is assessed per pinned distribution and dependencies (commonly BSD-family PX4/MAVSDK and GPLv3 ArduPilot); archive actual license files before redistribution. A sample's open-source license does not license a proprietary DJI binary. Review Parrot SDK and simulator licenses separately. No SDK bundle is copied in Phase 0.

## Companion-first recipe

1. Pin simulator/firmware and SDK commits in a separate reproducible environment; keep the flight-controller configuration under its operator's control. Use SITL without hardware first.
2. Attach a simulated or licensed recorded camera to the source worker. Feed Image/CameraInfo or bounded decoded frames; telemetry enters through an allowlisted observation interface. AETHRON sends no arm, mode, position, gimbal-follow or actuator messages.
3. Map camera exposure and autopilot clocks to a local trusted clock with measured uncertainty. A MAVLink TIMESYNC exchange can support mapping but is not automatic camera exposure synchronization. Reject out-of-order/future/stale frames and restart linkage on resets.
4. Choose onboard Linux compute with independent supervised processes, suitable payload mass/center-of-gravity/power/thermal design. CSI/UVC or vendor Ethernet camera access remains separate from the flight-control UART/CAN link.
5. Run camera interruption, telemetry interruption, CPU overload, timestamp drift and network-loss tests. Keep aircraft-native link-loss and pilot procedures intact; no AETHRON UNKNOWN event overrides a flight-controller failsafe.
6. When authorized for hardware, bench test without flight, then evaluate on a controlled operation with qualified personnel and applicable permissions. Measure the full power/latency budget and flight impact; do not extrapolate a desktop benchmark.

## Ground-station and cloud paths

Ground station can decode a legally exposed low-latency stream and show observations. Measure encode/radio/jitter/decode/inference latency from exposure, not receive time. Streams exceeding v3's 100 ms freshness budget remain delayed observation; do not weaken v3 to make radio video “live.” A future delayed-observation interface must have separate semantics and must not feed current safety recommendations.

Cloud supports optional artifact distribution or aggregate health. It is not the default image path or autonomous safety loop. On lost connection, companion/local sensing continues if its own valid evidence remains; ground UI expires and shows UNKNOWN. No buffered frames are replayed as fresh after reconnect. No flight behavior is requested just because a cloud service stops responding.

ROS QoS choice is an adapter requirement: sensor-data best-effort, keep-last small depth, compatible publisher/subscriber policies, deadline/liveliness monitoring and bounded executor work. Use source and receive stamps, not ROS message arrival alone. The research ROS QoS documentation fetch was bot-blocked; verify implementation against pinned middleware docs/code before committing exact QoS settings.

## External UAV detection lane

Compare a licensed small-object LWIR model with the retained classical and YOLOX baselines, and geometric Kalman/Hungarian versus greedy IoU/ByteTrack-style association. Solar loading, birds/fixed-wing aircraft, insects, few-pixel objects and intermittent misses are required negatives/challenges. No visual aircraft label becomes a UAV label. Never export weapon cues, persistent identity, target designation or autonomous following. Visage's qualitative PoC motivates tests but its range/accuracy does not transfer [S19](SOURCES.md#s19).

## Operations gate

Geofencing is an operator/flight-platform function and cannot be bypassed by this integration. Payload modifications can affect weight class, airworthiness and endurance. EU/EASA category, VLOS/airspace/night requirements; Swedish geographical zones and imagery dissemination; US FAA Part 107/Remote ID and other national rules apply conditionally [S38](SOURCES.md#s38)–[S41](SOURCES.md#s41). See [ASSURANCE](ASSURANCE.md). No simulator pass grants flight permission.

## Required onboard appliance operation

The [standalone appliance design](APPLIANCE-RUNTIME.md) is the normal onboard deployment, not a ground-station-dependent demo. Install verified runtime/model/plugin/config locally and enable the payload/vendor supervisor. After provisioning, disconnect laptop, ground station, phone and WAN/radio observation link; power-cycle the companion/payload and require autonomous local capture/inference/status with no command or online activation. Keep the physically required sensor bus/power intact. The flight controller's independent safety/link-loss behavior remains entirely its operator's responsibility.

Test A01–A09 first with pinned local simulator/recording and a real service-manager VM, later on the exact flight-compatible rig under authorization. Sensor/model loss, cold boot, repeated worker crash, thermal/power budget and offline recovery are required. Ground station/cloud remain optional consumers and cannot own the inference session. If a vendor API only exports imagery to an online/mobile controller, label it a ground-observation pathway, not standalone onboard support; use an authorized integrated payload camera/compute alternative where feasible.
