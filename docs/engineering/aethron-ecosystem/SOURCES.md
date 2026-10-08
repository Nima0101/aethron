# Primary-source research ledger — retrieved 2026-10-08

Versions distinguish selected references from current upstream candidates. Rolling pages are not immutable evidence. `read` means readable page content, `search_excerpt` means official publisher search extract only, `api` means public JSON metadata, and unavailable/empty pages support no affirmative feature claim. Recheck each rolling source and archive permitted terms/commit IDs before implementation. No vendor marketing numbers transfer to AETHRON. The detailed obligations of paid standards were not inspected.

## S01

[Apple CarPlay](https://developer.apple.com/carplay/) — rolling, retrieved 2026-10-08. Retrieved 2026-10-08; access: `read`.

Supported parked video now exists; category/entitlement and vehicle support still apply. No factory-camera API established.

## S02

[Android for Cars](https://developer.android.com/training/cars) — rolling. Retrieved 2026-10-08; access: `read`.

Android Auto projection differs from embedded AAOS; distribution categories and driving/parked restrictions apply. Do not infer camera access.

## S03

[Mazda 2019 Mazda3 manual](https://owners-manual.mazda.com/gen/en/mazda3/mazda3_8hs5ee19i.pdf) — 2019 regional manual. Retrieved 2026-10-08; access: `search_excerpt`.

Describes vehicle cameras/360 view. Exact Sport trim, market and factory video SDK not established. Large US manual retrieval also failed; do not infer connector pinout.

## S04

[SAE diagnostics scope](https://saemobilus.sae.org/standards/j1979_199607-e-e-diagnostic-test-modes) — J1979_199607 historical scope. Retrieved 2026-10-08; access: `search_excerpt`.

Emission-related diagnostic requests/responses are not generic camera transport. Current J1979-2 is a separate revision; this old abstract is not current compliance guidance.

## S05

[Android USB host/accessory](https://developer.android.com/develop/connectivity/usb) — rolling. Retrieved 2026-10-08; access: `search_excerpt`.

USB roles and power differ. Host/OTG support does not guarantee a UVC camera is exposed by Camera2.

## S06

[NVIDIA GMSL camera framework](https://docs.nvidia.com/jetson/archives/r36.3/DeveloperGuide/SD/CameraDevelopment/JetsonVirtualChannelWithGmslCameraFramework.html) — Jetson Linux r36.3. Retrieved 2026-10-08; access: `search_excerpt`.

Serializer/deserializer, sensor driver and device-tree integration required. A cable adapter cannot unlock proprietary OEM video.

## S07

[Raspberry Pi camera software](https://www.raspberrypi.com/documentation/computers/camera_software.html) — rolling libcamera/rpicam. Retrieved 2026-10-08; access: `search_excerpt`.

Use the modern camera stack; validate sensor/OS/driver tuple. Old raspicam recipes are not the selected path.

## S08

[V4L2 timestamp flags](https://www.kernel.org/doc/html/v4.9/media/uapi/v4l/buffer.html) — Linux API v4.9 reference. Retrieved 2026-10-08; access: `search_excerpt`.

Timestamp flags identify monotonic timing. Driver timestamp origin and exposure timing still need verification on current kernels.

## S09

[TI automotive power protection](https://www.ti.com/tool/TIDA-01167) — TIDA-01167. Retrieved 2026-10-08; access: `search_excerpt`.

Automotive supplies need transient, reverse-polarity, overload and load-dump protection. Reference design is not certification of an AETHRON installation.

## S10

[PX4 ROS 2 guide](https://docs.px4.io/v1.16/en/ros2/user_guide) — PX4 v1.16. Retrieved 2026-10-08; access: `read`.

Guide includes Ubuntu 22.04/Humble and Agent v2.4.3. Firmware and px4_msgs definitions must match; simulator clock bridge needs matching Gazebo integration.

## S11

[PX4 uXRCE-DDS](https://docs.px4.io/v1.16/en/middleware/uxrce_dds) — PX4 v1.16 / Agent v2.4.3. Retrieved 2026-10-08; access: `read`.

PX4 client v2.x is incompatible with Agent v3.x. Topics/board support depend on firmware configuration.

## S12

[ArduPilot companion computers](https://ardupilot.org/dev/docs/companion-computers.html) — rolling. Retrieved 2026-10-08; access: `read`.

Companion communicates MAVLink telemetry with autopilot. Cameras/pixels and command authority require separate integration.

## S13

[MAVLink camera protocol](https://mavlink.io/en/services/camera.html) — Camera Protocol v2. Retrieved 2026-10-08; access: `read`.

Stream descriptors identify URI/type/status; MAVLink does not guarantee frame-synchronized video metadata. Pixel transport must be negotiated separately.

## S14

[MAVSDK releases](https://api.github.com/repos/mavlink/MAVSDK/releases/latest) — v4.0.5 observed 2026-10-07. Retrieved 2026-10-08; access: `api`.

Upstream release metadata observed, not an AETHRON compatibility test. Pin release/commit and generated language bindings together.

## S15

[DJI Mobile SDK products](https://developer.dji.com/mobile-sdk/) — V5 family. Retrieved 2026-10-08; access: `read`.

Product list includes Mini 3/3 Pro/4 Pro, Mavic 3 Enterprise and several Matrice models. Support is per SDK/controller/firmware; not all DJI drones.

## S16

[DJI Android V5 release](https://api.github.com/repos/dji-sdk/Mobile-SDK-Android-V5/releases/latest) — V5.18.0 observed 2026-05-29. Retrieved 2026-10-08; access: `api`.

Exact upstream release observed. No equivalent iOS V5 support inferred; detailed features and vendor terms must be checked per tuple.

## S17

[DJI Payload SDK](https://developer.dji.com/doc/payload-sdk-tutorial/en/) — rolling. Retrieved 2026-10-08; access: `empty_dynamic`.

Public URL retrieved without readable content. Payload connector/electrical/activation/firmware matrix and redistribution terms remain unresolved; no compatibility commitment.

## S18

[Parrot Olympe](https://developer.parrot.com/docs/olympe/index.html) — 8.4.0. Retrieved 2026-10-08; access: `read`.

Linux SDK documents ANAFI family video-frame access and Sphinx simulation; prebuilt pip path is x86_64 desktop only. ARM requires separate source-build verification.

## S19

[Visage thermal UAV PoC](https://visagetechnologies.com/blog/uav-detection/) — 2026-04-28. Retrieved 2026-10-08; access: `read`.

Thermal small-object work discusses FLIT, Kalman/Hungarian, solar loading and SUAVE-600 v3. Qualitative vendor PoC is a hypothesis source, not independently reproducible AETHRON accuracy/range evidence.

## S20

[FLIR expanded thermal data](https://oem.flir.com/en-150/about/news/expanded-teledyne-flir-starter-thermal-dataset-for-adas-and-autonomous-vehicle-testing/) — expanded starter dataset announcement. Retrieved 2026-10-08; access: `search_excerpt`.

Thermal training candidate. Free access does not establish redistribution/model-commercialization rights; obtain current dataset agreement before download or bundling.

## S21

[KAIST multispectral dataset](https://multispectral.kaist.ac.kr/) — license/version unresolved. Retrieved 2026-10-08; access: `unavailable`.

Primary site inaccessible through research tool. Keep evaluation candidate only; no assumed permissive license or redistribution.

## S22

[FLIR thermal limitations](https://www.flir.com/en-gb/discover/home-outdoor/can-thermal-imaging-see-through-walls/) — rolling. Retrieved 2026-10-08; access: `search_excerpt`.

Conventional glass and opaque barriers obstruct LWIR; fog/rain can limit range. Thermal imaging is not precise through-wall perception.

## S23

[SWIR imaging physics](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/what-is-swir/) — rolling. Retrieved 2026-10-08; access: `search_excerpt`.

SWIR predominantly uses reflected radiation for ordinary scenes; do not treat it as passive LWIR or assume operation without appropriate illumination.

## S24

[TI mmWave sensing](https://www.ti.com/document-viewer/lit/html/SWRA766/GUID-677A83C2-703F-41D0-911F-158BBDFBA16F) — SWRA766. Retrieved 2026-10-08; access: `search_excerpt`.

mmWave offers nonvisible sensing. Vendor robustness statements are not our weather, resolution or class-accuracy qualification.

## S25

[ONNX Runtime execution providers](https://onnxruntime.ai/docs/execution-providers/) — rolling; local pin 1.30.0. Retrieved 2026-10-08; access: `read`.

Providers supply hardware-specific execution. Measure supported nodes, fallback, cold start, numerical equivalence and actual host performance.

## S26

[YOLOX source](https://github.com/Megvii-BaseDetection/YOLOX) — upstream main; existing model separately frozen. Retrieved 2026-10-08; access: `read`.

Apache-2.0 source candidate; preserve repository model digest. Detector family/license is not a trained thermal/UAV capability.

## S27

[ByteTrack source](https://github.com/FoundationVision/ByteTrack) — ECCV 2022 method / rolling source. Retrieved 2026-10-08; access: `read`.

Detection association baseline candidate, including lower-score observations. Preserve geometry-only path and frozen v3 continuation/expiry rules; do not import unrelated re-identification modules.

## S28

[TrackEval](https://github.com/JonathonLuiten/TrackEval) — rolling source. Retrieved 2026-10-08; access: `read`.

Reference HOTA evaluator candidate. Pin code before new evaluation; current frozen v3 frame-level metrics remain authoritative.

## S29

[OpenAPI](https://spec.openapis.org/oas/v3.1.1.html) — 3.1.1 selected, not claimed latest. Retrieved 2026-10-08; access: `read`.

Use JSON Schema-compatible typed HTTP contracts; transport schema cannot enforce trusted clocks or all temporal semantics.

## S30

[FastAPI features](https://fastapi.tiangolo.com/features/) — rolling; candidate 0.142.4. Retrieved 2026-10-08; access: `read`.

Typed validation, OpenAPI and ASGI ecosystem justify optional server boundary. Strict raw-byte duplicate/depth validation must precede framework parsing.

## S31

[PyPA TestPyPI](https://packaging.python.org/en/latest/guides/using-testpypi/) — rolling. Retrieved 2026-10-08; access: `read`.

Test index is distinct from production PyPI. Avoid dependency confusion via extra-index fallback; local wheel consumer is first gate.

## S32

[ROS Image](https://github.com/ros2/common_interfaces/blob/jazzy/sensor_msgs/msg/Image.msg) — Jazzy branch. Retrieved 2026-10-08; access: `read`.

Image carries encoding, dimensions, stride, header/frame information. Pair with CameraInfo and validate timestamps/size.

## S33

[ROS CameraInfo](https://github.com/ros2/common_interfaces/blob/jazzy/sensor_msgs/msg/CameraInfo.msg) — Jazzy branch. Retrieved 2026-10-08; access: `read`.

Calibration metadata and optical-frame conventions support adapter transforms; presence alone does not prove calibration validity.

## S34

[ISO functional safety](https://www.iso.org/publication/PUB200262.html) — ISO 26262:2018 family. Retrieved 2026-10-08; access: `search_excerpt`.

Conditional road-vehicle E/E functional-safety lifecycle. Public overview is not a clause-level compliance assessment or certificate.

## S35

[ISO SOTIF](https://www.iso.org/standard/77490.html) — ISO 21448:2022. Retrieved 2026-10-08; access: `search_excerpt`.

Functional insufficiency and foreseeable misuse require intended-domain validation beyond software correctness.

## S36

[ISO/SAE cybersecurity](https://saemobilus.sae.org/standards/isosae21434-road-vehicles-cybersecurity-engineering) — ISO/SAE 21434:2021. Retrieved 2026-10-08; access: `search_excerpt`.

Road-vehicle cybersecurity risk engineering; applicability determined by integrator/system scope.

## S37

[UNECE vehicle regulations](https://unece.org/media/transport/Vehicle-Regulations/press/352397) — UN R155/R156 overview, 2021. Retrieved 2026-10-08; access: `search_excerpt`.

Cybersecurity/software-update management regulations concern applicable type approvals; not an automatic requirement/certificate for every local library installation.

## S38

[EASA open category](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/open-category-low-risk-civil-drones) — rolling. Retrieved 2026-10-08; access: `search_excerpt`.

Category/aircraft/operation requirements govern EU trials. Review current national zones and operational authorization; perception is not flight permission.

## S39

[Swedish UAS operations](https://www.transportstyrelsen.se/en/aviation/aircraft/drones-unmanned-aircraft/guide-to-uas-operations-in-sweden/) — rolling. Retrieved 2026-10-08; access: `search_excerpt`.

Sweden-specific operations/airspace and imagery dissemination requirements need checking before trials/publication.

## S40

[FAA Part 107 operations](https://www.faa.gov/uas/commercial_operators) — rolling. Retrieved 2026-10-08; access: `search_excerpt`.

US commercial remote-pilot, night and airspace conditions apply where relevant; do not use EU assumptions in US deployment.

## S41

[FAA Remote ID](https://www.faa.gov/uas/getting_started/remote_id) — rolling. Retrieved 2026-10-08; access: `search_excerpt`.

Registration/Remote ID requirements and exceptions must be assessed for the aircraft and operation. Do not disable required broadcasts.

## S42

[EDPB video privacy](https://www.edpb.europa.eu/documents/guideline/guidelines-32019-on-processing-of-personal-data-through-video-devices_en) — Guidelines 3/2019. Retrieved 2026-10-08; access: `search_excerpt`.

Lawful basis, necessity, transparency and retention apply even without biometric identity. Consent is not automatically the only or sufficient lawful basis.

## S43

[Tesla Fleet API](https://developer.tesla.com/docs/fleet-api) — rolling. Retrieved 2026-10-08; access: `empty_dynamic`.

Primary URL yielded no readable API detail in tool. OEM-authorized API pathway remains possible, but no raw factory-camera endpoint or permission is established here.

## S44

[FastAPI package metadata](https://pypi.org/pypi/fastapi/json) — 0.142.4. Retrieved 2026-10-08; access: `api`.

Version candidate observed on research date; not installed, security-audited or qualified by Phase 0.

## S45

[Uvicorn package metadata](https://pypi.org/pypi/uvicorn/json) — 0.54.0. Retrieved 2026-10-08; access: `api`.

Candidate ASGI server version; dependency closure/platform wheel compatibility must be locked and tested in Phase 1.

## S46

[Pydantic package metadata](https://pypi.org/pypi/pydantic/json) — 2.13.5. Retrieved 2026-10-08; access: `api`.

Candidate strict envelope models; not a replacement for frozen byte parser.

## S47

[HTTPX package metadata](https://pypi.org/pypi/httpx/json) — 0.28.1. Retrieved 2026-10-08; access: `api`.

Candidate external consumer/test client, not a core dependency.

## S48

[Visage Edge AI](https://visagetechnologies.com/edge-ai/) — rolling. Retrieved 2026-10-08; access: `unavailable`.

Linked from PoC; web tool fetch failed. No performance or deployment claim derived from unavailable contents.

## S49

[Visage AI safety](https://visagetechnologies.com/ai-safety/) — rolling. Retrieved 2026-10-08; access: `unavailable`.

Linked from PoC; web tool fetch failed. No certification or assurance inferred.

## S50

[Visage autonomy](https://visagetechnologies.com/autonomy/) — rolling. Retrieved 2026-10-08; access: `unavailable`.

Linked from PoC; web tool fetch failed. AETHRON safety floor overrides vendor capability breadth.

## S51

[Dist-Tracker / FLIT paper](https://openaccess.thecvf.com/content/CVPR2025W/Anti-UAV/papers/Wang_Dist-Tracker_A_Small_Object-aware_Detector_and_Tracker_for_UAV_Tracking_CVPRW_2025_paper.pdf) — CVPR Workshops 2025. Retrieved 2026-10-08; access: `search_excerpt`.

Publisher excerpt describes L2/IoU association for small objects. Full PDF retrieval returned 403; do not assume uninspected implementation details or transfer results.

## S52

[Anti-UAV challenge data](https://anti-uav.github.io/dataset/) — 4th challenge. Retrieved 2026-10-08; access: `read`.

Primary challenge describes thermal crossover, dynamic backgrounds, scale and multiple-UAV sequences. Data access terms must be distinguished from repository code license.

## S53

[Anti-UAV repository license](https://github.com/ZhaoJ9014/Anti-UAV/blob/master/LICENSE) — MIT repository license. Retrieved 2026-10-08; access: `read`.

MIT code license observed; verify terms of each separately hosted data archive before redistributing images or trained artifacts.

## S54

[Electrical loads](https://www.iso.org/standard/76119.html) — ISO 16750-2:2023. Retrieved 2026-10-08; access: `search_excerpt`.

Road-vehicle electrical-load scope explicitly excludes motorcycle/moped environmental testing and does not cover EMC; do not apply indiscriminately.

## S55

[Laser safety](https://webstore.iec.ch/en/publication/3587) — IEC 60825-1:2014. Retrieved 2026-10-08; access: `search_excerpt`.

Laser product classification/requirements potentially apply to LiDAR/active sensors. Final assembled product needs assessment; module label alone is insufficient.

## S56

[Lamp/LED photobiological safety](https://webstore.iec.ch/en/publication/7076) — IEC 62471:2006. Retrieved 2026-10-08; access: `search_excerpt`.

Optical lamp/LED safety scope differs from lasers. Assessment needed for active NIR installation and exposure geometry.

## S57

[OpenCV Kalman primitive](https://docs.opencv.org/3.1.0/dd/d6a/classcv_1_1KalmanFilter.html) — 3.1.0 API reference, historical. Retrieved 2026-10-08; access: `search_excerpt`.

Standard Kalman primitive illustrates library alternative; does not establish current 4.13 numerical/ABI equivalence to frozen core.

## S58

[MAVSDK license](https://raw.githubusercontent.com/mavlink/MAVSDK/main/LICENSE.md) — rolling license retrieved directly. Retrieved 2026-10-08; access: `read`.

BSD three-clause text retrieved and hashed locally; capture exact release license when redistributing dependencies.

## S59

[Public AETHRON main](https://api.github.com/repos/Nima0101/aethron/commits/main) — 59fda946771d4ac8c9d1b52eeb3d948215325e4c. Retrieved 2026-10-08; access: `api`.

Direct anonymous HTTP retrieval confirmed baseline main SHA; no repository mutation.

## S60

[Public AETHRON Camera](https://nima0101.github.io/aethron/) — HTML SHA-256 in baseline evidence. Retrieved 2026-10-08; access: `read`.

Direct HTTP 200 AETHRON HTML response; no browser/device-camera, service-worker, offline-cache or inference execution claimed.

## S61

[Apple background capture interruption](https://developer.apple.com/documentation/avfoundation/avcapturesession/interruptionreason/videodevicenotavailableinbackground) — rolling. Retrieved 2026-10-08; access: `search_excerpt`.

Apple documents camera interruption in background. No generic unattended auto-boot camera app entitlement is inferred; supported special platform contexts require exact API/entitlement review.

## S62

[Android foreground camera services](https://developer.android.com/develop/background-work/services/fgs/service-types) — Android 14+ service types / rolling. Retrieved 2026-10-08; access: `read`.

Camera while-in-use permission constrains background and BOOT_COMPLETED launches, with documented exceptions. Do not claim arbitrary camera auto-start on consumer phones.

## S63

[systemd service reference](https://github.com/systemd/systemd/blob/v255/man/systemd.service.xml) — v255 reference. Retrieved 2026-10-08; access: `read`.

Service restart/watchdog semantics inform planned boot package. Actual distro build must be pinned and tested; process watchdog does not substitute for scene freshness.

## S64

[systemd execution isolation](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml) — v255 reference. Retrieved 2026-10-08; access: `read`.

Service privilege/filesystem/device isolation is profile-specific; required camera/device access must remain explicit. No unit installed in Phase 0.

## S65

[Windows job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) — Windows 8+/Server 2012+ nested jobs; page 2025-07-14. Retrieved 2026-10-08; access: `read`.

Worker-local unnamed job with kill-on-close contains descendant processes; no breakaway or unrelated host process enumeration. Native Windows execution remains pending.

## S66

[Windows extended job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information) — Win32 JOBOBJECT_EXTENDED_LIMIT_INFORMATION. Retrieved 2026-10-08; access: `read`.

SDK ABI reference for ctypes wrapper outside the frozen core; target Windows CI must execute the crash regression before declaring support.
