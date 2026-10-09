# True zero-visible-light sensing and calibration

“Zero visible” means no usable visible illumination at the scene; active nonvisible illumination may still be present. Report visible-band meter sensitivity/uncertainty, spectral illumination and sensor exposure. A rendered black RGB frame proves software suppression, not physical darkness or nonvisible performance. v3 conservatively accepts RGB only in `daylight`; nonvisible support may continue in all lighting states if independently valid.

## Modalities and failure hypotheses

| Modality | Zero-visible mechanism | Required evidence / limitations |
|---|---|---|
| RGB | None without visible photons | Suppress in blackout; gain/denoise cannot fabricate evidence |
| Active NIR | NIR-sensitive sensor, suitable lens/filter and illuminator | Wavelength/beam/exposure/eye-safety assessment, reflectance/distance/fog/backscatter; IR-cut RGB cameras may reject it |
| LWIR thermal | Passive thermal radiation contrast | Temperature/contrast/NETD/optics/NUC behavior, solar loading/crossover/hot backgrounds; ordinary glass blocks view; no monocular metric depth [S22](SOURCES.md#s22) |
| SWIR | Reflected SWIR/nightglow or active illumination | Not equivalent to passive LWIR; absent sufficient SWIR photons needs illumination, sensor/optics and cost justification [S23](SOURCES.md#s23) |
| mmWave radar | Active RF ranging/motion | Antenna/FOV/range-angle resolution, multipath/ghosts/interference, material/geometry, SDK point/object semantics; no human identity; weather claim measured [S24](SOURCES.md#s24) |
| ToF/active stereo/LiDAR | Emitted nonvisible light and timing/pattern | Eye safety, emitter interference, reflective/dark/transparent surfaces, rain/fog, sun saturation, time sync |
| Passive stereo | Corresponding visible/nonvisible images | Requires texture and photons; ordinary passive RGB stereo fails in complete darkness |
| IMU | Ego-motion support | Bias/time/extrinsic calibration; motion is not evidence that an object exists |

A thermal palette/video is not automatically radiometric temperature. Preserve raw bit depth and scaling where authorized; do not call normalized intensity degrees Celsius. NIR reflectance is not thermal temperature. Low-angular-resolution radar does not inherently provide an image box: only emit registered v3 geometry with validated projection/uncertainty. Unregistered or ambiguous radar can retain coarse permitted information through its appropriate separate contract, never precise hidden-person v3 tracks.

## Calibration recipe

1. Record sensor/firmware/driver/optics, exposure mode, resolution, FOV and timestamp origin. Freeze representative raw sample hashes and preprocessing version.
2. Calibrate intrinsics/distortion at the operational focus/resolution. Use targets visible to the actual modality; a printed checkerboard may not have thermal contrast.
3. Measure inter-sensor extrinsics against a common frame, reprojection residual distribution and timestamp offset/drift. Physical hardware trigger/PTP can help, but USB/driver support must be tested.
4. Build a versioned calibration record with device tuple, transforms, residuals/covariance, conditions and expiry/revalidation triggers. Recalibrate after remount, resolution/lens change or mechanical shock.
5. Convert exposure clocks with conservative uncertainty bounds. For sensor age use worst-case age; for inter-support skew include both error bounds. Missing mapping/calibration suppresses localized fusion, not merely a warning badge.
6. Validate projected boxes on held-out paired scenes; do not calibrate against evaluation labels at inference. Crossings/occlusion and parallax expose false matches. Current core allows only mutually unique cross-sensor same-class matches with frozen IoU rules.

V3 registration is one image plane, not a universal 3D world model. SWIR has no dedicated v3 kind: keep an independent research adapter until a versioned semantic mapping/amendment is approved; never relabel it LWIR to bypass enums. Multiple physical sensors of the same kind likewise require a reviewed upstream consolidation or new protocol; v3 permits five unique kinds, not arbitrary camera IDs.

## Zero-light test campaign

| Scenario | Offline/system-in-loop check now possible | Later physical measurement |
|---|---|---|
| Daylight → RGB blackout, valid LWIR | Same ephemeral track with truthful LWIR provenance; no RGB support | Measured illumination, thermal contrast and calibrated boxes |
| NIR source on/off, low-reflectance clothing | Valid NIR retains track; emitter loss invalidates support | Spectrum, exposure, eye-safety evidence, range-dependent FN |
| Radar/depth remaining after image loss | Keep only supported geometry/range; ambiguity UNKNOWN | Registered localization error and multipath/interference |
| All modalities lost | UNKNOWN, no prediction birth, stale state deletion | Disconnect/power-loss watchdog and UI expiry latency |
| Thermal crossover/solar loading | Model low-confidence/missed detections preserved | Heated backgrounds, dawn/dusk, varied temperature/humidity |
| Rain/fog/spray/dirty window | Mark injected quality fault and stale frames | Controlled weather samples and lens contamination; no blanket all-weather claim |
| Clock skew/buffer delay | Reject >50 ms skew or >100 ms age including uncertainty | Exposure-to-output measurement, drift and reboot |
| Crossing/short occlusion/re-entry | Uncertain association; ≤500 ms persistence, new ID after expiry | Representative moving-camera scenes; predictions never scored as observations |

Record per-class FP/FN, miss duration, localization error, abstentions, confidence calibration, p50/p95/p99/max full-pipeline latency, dropped/stale fraction, RSS, power and ambient temperature. Define acceptance thresholds and intended domain before evaluation; no numeric field accuracy or physical range target is invented here. Missing physical testing blocks that claim while software work proceeds.

## Datasets and models

Existing AOT bytes/labels/licenses/hashes remain immutable and evaluation-only; tiny fixed-wing aircraft are not UAV ground truth. FLIR thermal data is a training/evaluation candidate with terms to acquire [S20](SOURCES.md#s20). KAIST licensing could not be verified from the unavailable primary site [S21](SOURCES.md#s21); do not bundle. SUAVE-600 v3 and Anti-UAV are leads named by Visage, not licensed dependencies in this plan; verify original publisher, exact release, annotations, terms and train/test provenance before use. Nighttime images alone do not prove zero visible illumination.

Split by capture session/location/rig/weather, not adjacent frames. Keep training/validation/test separate, record model training-data overlap risks, double-check labels without tuning on test outcomes, retain negative clips and dataset hashes. Freeze detector/preprocessor/threshold/provider before held-out evaluation. Add HOTA using a pinned reference evaluator for new sequence studies while retaining the frozen v3 metrics [S28](SOURCES.md#s28). No trained thermal/UAV model is selected without these checks.
