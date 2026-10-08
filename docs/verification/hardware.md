# Hardware and platform evidence
Camera and USB enumeration both returned empty device lists on this host. No physical sensing device was exercised. Do not treat host CPU execution as sensor validation.

| Claim | Evidence | Exact blocker |
|---|---|---|
| Local Python software semantics | macOS arm64; Python 3.9.6 and 3.13.15 executions recorded | no real-time guarantee |
| Linux/Windows runtime | CI workflow prepared | hosted runs not yet executed |
| Radiometric thermal | synthetic Celsius patches only | exact sensor/firmware, calibration source, emissivity/range/occlusion/darkness trials |
| RGB person detection | minimized synthetic scores/rectangles only | reviewed licensed model and consented held-out physical scenes, FP/FN/calibration |
| Thermal/depth person envelopes | synthetic minimized cues only | validated classifier/localizer per exact device, registration/ambiguity/zero-light tests |
| Active depth obstacle | synthetic metre patches only | exact LiDAR/depth technology, dark/reflective/saturated scenes and clock evidence |
| Radar through-obstruction | synthetic coarse sectors only | actual module/firmware, authorized site, material-specific penetration/noise/multipath validation and independent privacy review |
| iOS/Android | protocol target; no device driver claim | device/runtime/permissions/entitlements and physical sensor validation |
| Vehicle/drone controller | recommendation fixture only | independent controller contract, watchdog and hardware-in-loop defensive action validation |

No live sensor acquisition, live inference speed, power/thermal envelope, hardware recording or field accuracy evidence exists. Live-demo command is intentionally absent rather than inventing a camera feed. A physical integration team must supply calibrated, minimized observations and named-device test results to close H02/H03. UNKNOWN never authorizes continued motion.
