# Owner requirement — permanent, autonomous AETHRON appliance runtime

**Owner instruction added 2026-10-08. Priority: product-defining and mandatory for Phase 0 NEXT, Phase 1 planning and subsequent implementations. This document is an architectural/product requirement, not an implementation or a claim of safety qualification.**

## Principle

The expected **ordinary end-user experience** is: **one-time installation/commissioning → power on → AETHRON starts and operates locally, continuously, unattended**.

After installation, a working supported AETHRON unit must **not require** any user-connected laptop/desktop, tethered smartphone, ongoing USB connection to a programming host, terminal, manual `pip`/Docker command, third-party control server, cloud subscription, Supabase, Coolify, network access, internet connection, or remote login in order to acquire sensor data, perform on-device inference/sensor fusion and present *locally available* state. Phone apps, developer laptops, USB provisioning cables, cloud consoles and remote APIs may support optional configuration, maintenance and presentation. Unplugging or losing those optional endpoints after commissioning must not disable the local perception loop.

**Do not interpret this as operation without any power, compute, sensor, installation wiring or physically needed data bus.** Those resources must be integrated inside the host hardware or permanently installed by an appropriate authorized process. A valid internal USB camera bus or secured sensor connector is not the prohibited \"external laptop USB tether\". Where hardware does not support local installation and the OEM cameras are inaccessible, a professionally integrated, compact, fixed-power retrofit appliance with its own approved camera/sensor is a legitimate deployment class; do not falsely promise software-only enablement of locked OEM video.

## Primary, preferred deployment modes

1. **OEM/embedded native integration**: AETHRON installs within an OEM-authorized infotainment/ADAS/vehicle compute environment *only if* documented APIs, hardware budgets and permission make camera access available. The OEM OS/service manager handles boot, updates and lifecycle; driver control is never inferred.
2. **Permanent vehicle edge appliance (universal retrofit pathway)**: A compact sealed compute/NPU board or production-ready existing edge device, permanently mounted and correctly powered/protected from automotive supply; wired/securely paired to compatible cameras/thermal/depth/radar modules. No removable laptop, no dangling user USB lead. Ignition/accessory lifecycle, power interruption, reboot, sleep/wake, brownout recovery and independent fault reporting are first-class. Tested environmental tolerances and harness certification remain per hardware installation.
3. **Drone on-board integration**: Companion/onboard compute with persistent AETHRON service/image and integrated camera/payload stream. It boots with supported drone/payload power, requires no ground-station laptop or live radio link for local inference, and remains strictly observation/assistance unless separately qualified. UAS flight controller ownership and flight safety are independent.
4. **Home/smart-camera installation**: On-device package/container when supported, or permanently operating NVR/NAS/camera hub/edge module with local camera feeds; power/PoE local LAN is part of the fixed installation. No day-to-day PC, external monitor, phone session or internet dependence.
5. **Consumer phone/native app**: AETHRON can run on an iPhone/Android when the device itself is actively running a permitted camera session, subject to the mobile OS lifecycle. It cannot promise background persistent camera operation in violation of iOS/Android restrictions. A phone is not required as a continuous companion to modes 1–4.

**The primary sales/installation story must not be `pip install` + `aethron camera --source 0` + laptop tether.** Those remain developer/service/debugging entry points. A consumer obtains a preinstalled compatible product, OEM-approved deployment, signed downloadable runtime/firmware or guided one-time provisioning of a permanent appliance.

## Standalone runtime architecture

```text
Embedded device boot / vehicle ignition / drone payload on / camera hub on
    -> systemd / launch service / embedded supervisor / vendor platform manager
    -> verified, signed AETHRON runtime and immutable/configured model artifacts
    -> sensor capability discovery, permissions, calibration/clock and health check
    -> supervised local capture -> edge inference -> bounded fusion
    -> local event/API/UI or independent built-in visual/audible notifier
    -> offline monitoring, bounded logging and recovery
```

Hard requirements for implementation:
- Signed reproducible image/package/firmware, versioned plugin ABI and provisioning instructions for suitable target OS/CPU/GPU/NPU without mandatory third-party account.
- `enabled` auto-start unit/service at normal boot and deterministic restart strategy for worker crashes; clean interruption, no unbounded restarts or stale observations retained; safe degraded/UNKNOWN state if any essential camera/sensor/model disappears.
- No license-server heartbeat or online activation required to start perception. Model files, calibration and rules available locally, integrity-verified before use. Optional updates download only when requested/authorized and never block steady-state operation.
- Local onboarding may use temporary Bluetooth/Wi-Fi/LAN/USB or an app, but prove **post-provision untethered** mode by disconnecting provisioning laptop/phone, cutting WAN and restarting the system.
- Unattended operation accounts for power, ignition ACC, battery drain, watchdog, thermal throttling, filesystem wear, tamper/security, persistent local device identity, disk-full and CPU/NPU failure; preserve event freshness and frame provenance.
- Provide local diagnostics/service mode and recoverable factory-reset/provisioning procedures, without sending raw camera images to vendor cloud by default.
- Human alerts are bounded by actual verified modality and environment; never represent unqualified prediction as field-validated vehicle/drone emergency response.
- For **total visible darkness**, sensor self-test and calibration must confirm an independent nonvisible sensing modality and suitable optics; RGB-only enters explicit `UNAVAILABLE` or `UNKNOWN` if it cannot observe. Do not pretend software can create missing thermal/radar evidence.

## Acceptance criteria to put in PHASES and implementation backlog

Each supported deployment class needs at least these reproducible tests (first simulated/software-in-loop, then hardware as available):
1. **One-time provision**: install/connect only during setup; disconnect user's phone/laptop/USB host and close provisioning software; reboot. The provisioned device starts AETHRON automatically with no user command.
2. **No-WAN and companion independence**: remove internet, stop optional cloud/backend, disable phone Bluetooth and Wi-Fi; confirm sensor capture, inference, local event subscription/UI and expiry still work, including after cold reboot.
3. **Power lifecycle**: cold boot and ignition/payload wake, sleep/restart, transient undervoltage and unclean shutdown; check startup timing and stable recovery; require correct nonvolatile configuration and no spurious SAFE state.
4. **Sensor interruption**: physically unplug or simulate loss of only *allowed hardware sensor* during bench testing, stale/delayed/black frames and transport reconnection; event state becomes UNKNOWN/DEGRADED and only resumes after bounded fresh evidence; never treat stale boxes as current.
5. **Transport and thermal budget**: run representative camera formats and inferenced workloads for meaningful duration at actual target power/temperature, reporting p50/p95/p99 end-to-end acquisition+inference+publication latency and device uptime. Device qualifications require real SKU and capture clocks, not just synthetic replay.
6. **Multiple platform recipes**: native embedded install; sealed vehicle retrofit; drone payload/companion; home NVR/smart camera. Record exact supported hardware/software/driver combinations and one-page normal-user guides with auto-start/diagnostics/recovery.
7. **Real no-light evidence**: verify camera modality and optical path in zero visible light and fail explicitly if unsupported. Qualified safety claims additionally require held-out representative field trials and independent assessment.

## Architectural decisions/phase sequencing

- Phase 0 must explicitly prioritize this runtime model in `START_HERE.md`, `ARCHITECTURE.md`, `VEHICLE-COMPATIBILITY.md`, `DRONE-COMPATIBILITY.md`, `PACKAGING.md`, `WORKFLOW.md`, `TEST-EVIDENCE.md`, `IMPLEMENTATION-BACKLOG.md` and `PHASES.json`. Cross-link to this owner requirement and record what is proposed, implemented or measured.
- Phase 1's proposed API install/edge-service work must be **designed from day one as a headless, supervised embedded runtime with auto-boot**, even if initial coding tests use a PC as development host. Early acceptance should include a service-manager installer/autostart harness, offline/no-laptop integration test, local API consumer and reproducible edge image candidate.
- Subsequent stages implement OEM-specific vendor integrations, production installer/firmware provisioning, hardware matrices, drone/vehicle mounts and manufacturing quality; absence of test hardware is not permission to stop software adaptation but must be visible as a qualification gate, not hidden.
- Native mobile companion and desktop developer tools remain optional clients; they do not own the device's continuous inference session.
- **Phase 0 remains documentation/workflow only. The owner alone decides when to START Phase 1. No implementation, no push/merge, no deployed change at this stage.**
