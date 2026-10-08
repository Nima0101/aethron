# Sensor capability matrix v1
| Sensor | Permitted reference feature | Mandatory withdrawal | Live evidence prerequisite |
|---|---|---|---|
| Visible camera | already minimized transient presence cue | darkness, occlusion, model failure/timeout | exact camera, reviewed model/data, held-out accuracy, lighting tests |
| Thermal | coarse hot/cold/fire-like anomaly | saturation, stale calibration, invalid range | radiometric device, emissivity/environment protocol, temperature reference |
| Depth/LiDAR | coarse near obstacle/free-space cue | invalid range, occlusion, missing frames | exact range unit and scenes, reflectance/dropout evidence |
| Radar/mmWave | authorized coarse sector occupancy | multipath/noise, authorization absent | exact module/firmware, coarse zone validation and privacy review |
| IMU/GNSS | future context only, not person localization | absent/unreliable | device and clock tests before implementation |
| Environment | future hazard cues only | calibration/quality absent | exact sensor and measured protocol |

No live platform is claimed at freeze. Linux edge, phones, vehicle and drone compute are architecture targets; CI and hardware-in-loop must precede each support claim. Native mobile SDK/entitlement integrations are blocked until those resources exist. Reference adapters may consume explicitly synthetic or externally minimized data; neither establishes physical sensor support.
