# Vehicle compatibility — generic paths, exact evidence

No vehicle is production-supported by this plan. Mazda is one example. Powertrain (gasoline/diesel/hybrid/EV) does not determine camera access; model year, market, trim, ECU/infotainment firmware, connector, SDK entitlement and contract matter. Vehicle operation remains independent of AETHRON observation. A recommendation is never wired to brakes/steering in Phase 1.

## Decision tree

1. Is there a documented, owner-authorized OEM camera API/export for the exact vehicle and use? Record endpoint/SDK version, permissions, terms, format, capture clock and availability while parked/driving. If yes, develop an adapter and exercise it against sandbox/recordings, then the actual tuple. If no or unknown, proceed to your own camera. Do not bypass DRM, authentication, gateways or safety wiring.
2. Is the camera yours or explicitly authorized? Identify UVC, CSI, GMSL, IP/RTSP or vendor USB/Ethernet transport. A USB connector may carry power only; a Wi-Fi camera may require a proprietary app and expose no RTSP.
3. Can the selected host decode it with trustworthy timing and calibration? Enumerate format/resolution/fps, capture timestamp origin, driver/firmware and device permission. If latency cannot be bounded, offer delayed observation with UNKNOWN freshness, never timestamp it anew.
4. Is zero-visible operation required? Add a compatible physical nonvisible sensor and appropriate optics/illumination. A phone camera or dashcam marked “night vision” does not establish zero-light capability. Use [SENSOR-NIGHT](SENSOR-NIGHT.md).
5. Do mounting, power, thermal, privacy and driver-distraction requirements pass the vehicle/site assessment? If not, keep bench/replay work moving while installation remains blocked.
6. Validate the full tuple and intended domain using [TEST-EVIDENCE](TEST-EVIDENCE.md), then assign the narrow evidence level. A passing UVC adapter does not qualify every UVC product.

## Access mechanisms

| Path | What the implementer can build | What needs exact proof |
|---|---|---|
| UVC USB | V4L2 Linux, AVFoundation macOS or Media Foundation Windows acquisition worker | Supported formats, USB bandwidth, clock origin, reconnect, permissions |
| Android USB OTG/host | USB permission/host capability probe; supported external Camera2 or reviewed UVC library | Phone SKU, power budget, cable/PD role, OS external camera HAL; OTG alone insufficient [S05](SOURCES.md#s05) |
| iPhone/iPad accessory | Consume native-owner camera/approved accessory interface | Platform/connector/vendor support; no generic iPhone UVC promise |
| CSI ribbon | Linux libcamera/Picamera2 worker | Board connector/lane/driver/device-tree and sensor version [S07](SOURCES.md#s07) |
| GMSL automotive camera | Vendor deserializer/serializer and camera driver on supported edge board | Matched sensor/power/coax/firmware and calibration; not generic USB [S06](SOURCES.md#s06) |
| IP/RTSP over Ethernet/Wi-Fi | Isolated authenticated decoder, bounded latest frame, timeout/reconnect | Actual stream URI/codec/credentials, PTS mapping, network loss/jitter; ONVIF/RTSP not universal |
| OEM factory camera | SDK-specific adapter only with documented access | OEM authorization, license, firmware, integrity/safety restrictions; otherwise unsupported |
| OBD-II/CAN/J1939 | Authorized telemetry adapter or hardware listen-only interface | Signals/DBC rights/rates/gateway; diagnostic reads may transmit requests; never advertise electrically passive unless true |

OBD-II is diagnostic access, not camera video [S04](SOURCES.md#s04). CAN telemetry cannot be assigned to video pixels without timestamp and transform evidence. “Read-only” API means no state-changing calls, but may still emit network requests; passive CAN requires actual listen-only hardware/configuration. Do not scan arbitrary buses or perform security unlocking.

CarPlay and Android Auto are UI ecosystems with categories, permissions and driving-state restrictions. Apple's current page includes parked video in supported cars [S01](SOURCES.md#s01); Google distinguishes projection from AAOS [S02](SOURCES.md#s02). Neither is a factory-camera entitlement. An OEM AAOS system integration may expose privileged interfaces to approved partners; a normal installed app cannot assume those privileges. No live safety overlay on a driving display is promised.

## Installation recipes — implementation targets

These are actionable preparation recipes, not instructions to install a nonexistent released edge package. The proposed software commands are in [PACKAGING](PACKAGING.md); existing host preview is documented in [current camera guide](../../usage-live-platforms.md).

### A. Commissioning an older ICE passenger-car appliance; no OEM access

1. Inventory an external UVC daylight camera, rigid unobtrusive mount, short data cable, laptop/mini-PC and regulated portable supply. Keep the vehicle camera/ADAS wiring untouched.
2. On the bench, install the release wheelhouse and run replay/doctor; open only the camera device granted by the OS. Select a supported fixed format and characterize capture delay.
3. Mount away from sightlines, airbags and OEM camera/radar fields; secure wiring against pedals/steering and crash movement. Record measured placement/calibration and rerun registration after movement.
4. Power from a properly rated protected accessory supply or independent battery. Verify fuse/current limits, low-voltage cutoff, startup/shutdown and temperature at intended ambient conditions.
5. Confirm daylight objects and unplug/cover/stall responses on a stationary rig. A zero-visible claim needs an externally mounted LWIR or validated active NIR/depth/radar system.
6. Display only observation/uncertainty to a passenger or parked user until an authorized distraction/field protocol allows more. No automatic braking.

Outcome: verified bench bring-up feeding the permanent appliance recipe below; portable compute is a commissioning tool, not a required daily companion. No factory-camera dependency or driving guarantee.

### B. Modern hybrid/EV, including Tesla-like API ecosystems

1. Use the same retrofit camera/compute path; identify the low-voltage system and approved accessory connection from the vehicle manual. Never connect to traction/high-voltage circuits.
2. Treat an OEM fleet/cloud API as a separate authorized telemetry source. Tesla's public API page does not establish an AETHRON raw-camera route [S43](SOURCES.md#s43).
3. Test vehicle sleep/wake and standby battery drain; cloud rate limits/outages must not block local perception. Do not wake or control the vehicle as an incidental side effect.
4. Qualify installed cameras and clocks separately from vehicle telemetry. Keep the UI off a restricted driving display.

Outcome: local observation independent of cloud/OEM camera availability, with optional proven telemetry context.

### C. Truck/bus/fleet installation

1. Inventory each body/upfit, actual nominal supply (often different from passenger cars), approved mounting zones and installer requirements. Never assume a 12 V adapter suits a 24 V vehicle.
2. Prefer a rugged Linux edge box, authorized Ethernet camera network or matched GMSL kit, suitable fusing/isolation and environmental enclosure. Existing fleet cameras may be recorder-only: obtain a documented export first.
3. Segment the camera network from vehicle control and enterprise networks. Install certificates/config by asset administrator; send only aggregate health to the fleet console.
4. Evaluate vibration, long cable runs, rain/washdown, reboot/brownout, thermal soak, EMC and night scenes. Review workforce/passenger privacy notices and retention policy before any capture.
5. Qualify each changed camera/firmware/upfit tuple, not one whole manufacturer. Optional J1939 telemetry needs authorized signals and a receive-only design where practicable.

Outcome: managed edge fleet observation; no fleet-wide compatibility from one bus test.

### D. Motorcycle, small utility vehicle, off-highway machine

1. Verify legal mounting, rider distraction, vibration, water/impact exposure and available protected power. Avoid helmet modifications without relevant safety approval.
2. Choose mechanically secured compact compute/camera or a parked/observer phone interface. No dangling cables or assumed fan cooling in a sealed hot enclosure.
3. Test roll/pitch/camera rotation explicitly: v3 translation-only compensation cannot establish reliable physical velocity through these motions.
4. If safe installation or timestamp/calibration stability is infeasible, record the exact unsupported tuple and continue portable bench/software work.

### E. Custom embedded box / desktop development rig

Mac/Windows/Linux laptop gives easy debugging and portability tests; Linux mini-PC offers service supervision; Raspberry Pi-like boards offer camera interfaces and constrained compute; Jetson offers supported GPU paths at added power/cooling/runtime cost. Select by measured end-to-end latency and supply/thermal budget, not TOPS marketing. Benchmark decode, transfers, inference, fusion and UI separately. No SKU, throughput, wattage or range is promised by this plan.

## Installer evidence record

Required fields: vehicle make/model/year/market/trim (VIN retained privately only if necessary), host OS/arch/firmware, camera/optics/firmware/driver, connector/power protection, calibrated mount transform/date, clock source/error, model/provider digest, ambient/light/weather domain, frame/drop/latency/RSS/power measurements, fault response, permissions/terms and test report digest. Public evidence redacts serials, exact location and identifiable imagery. Bench evidence stays useful even before a physical vehicle is available.

## Primary consumer/fleet recipe: permanent autonomous appliance

The portable bench/commissioning recipes above lead to the normal installation defined by the [owner requirement](OWNER-NEXT-APPLIANCE-RUNTIME.md); a permanently tethered laptop or phone is not the intended product. Prefer OEM-authorized embedded compute only when camera/OS access and signed deployment rights are documented. Otherwise install a fixed edge appliance with its own permitted sensors; proprietary camera limits do not prevent that class.

1. Select an exact rugged compute/sensor tuple with offline model/SDK rights, local status indicator, sufficient measured power/cooling and a protected ignition/accessory lifecycle design.
2. Have the appropriate installer secure enclosure, mounts, harness and power protection; do not modify control/ADAS circuits or traction-voltage wiring. Internal/fixed USB camera buses are permitted; a developer-host tether is not required.
3. Provision the signed image/service once using a temporary tool. Store verified weights/config/calibration locally and enable boot supervisor with bounded recovery.
4. Remove the provisioning laptop/phone, close all client sessions and cut WAN. Cycle ignition/device power; require local capture, inference, status/API and UNKNOWN/expiry to work with no login or command.
5. Test sensor loss, nonvisible loss, power interruption, thermal soak, disk-full and update recovery per A01–A09. Physical claims require exact-device results; VM/recorded testing can precede the rig.

The driver's normal guide is power/status/recovery and a clear scope of assistance. Optional phone/fleet clients observe or maintain the device; their absence cannot stop it. Each passenger-car, EV/hybrid, fleet/bus/truck or motorcycle installation gets its own protected-power/mount/privacy/environment assessment and one-page guide. [APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md) owns the common gate and operator/installer boundary.
