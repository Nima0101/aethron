# Capability matrix v3 (additive)
| Evidence/input | Day | Zero visible light | Geometry/motion | Qualification boundary |
|---|---|---|---|---|
| RGB semantic detection adapter | Yes | Suppressed | Current boxes; bounded tracks | No bundled field-qualified semantic weights |
| LWIR semantic adapter | Yes | Yes if valid | Same ordinary sensor plane | Requires class-trained detector; temperature alone is not identity/class |
| Radar registered object adapter | Yes | Yes | Boxes only with validated ordinary-scene projection, range | Multipath/noise/calibration reject; physical validation pending |
| Active depth/LiDAR | Yes | Yes if sensor valid | Range and registered localization | Sunlight, material, range and eye-safety limits device-specific |
| NIR active input | Yes | Yes if valid | Adapter geometry | No assumption that passive NIR works without illumination |
| Ego translation | Yes | Yes if validated | Compensated image motion, not world velocity | Rotation/parallax unsupported; unknown on invalid transform |
| Coarse authorized obstruction radar v2 | Yes | Yes if valid | Zone presence only | Never passed into v3 tracker |
| Original synthetic sequences | Yes | Simulated | All allowed classes/short occlusion | Semantics and integration only |
| Licensed AOT grayscale recording | Recorded conditions only | Not established | Classical obstacle proposals + tracker | Not thermal, not proof of UAV class or local hardware |

person/cyclist/vehicle/uav/animal/obstacle/equipment/hot/cold/fire_like/smoke are schema and adapter classes, not claims of learned-detector accuracy. Scene-local tracks expose temporary boxes/confidence/range/relative image motion/prediction only. All sensor-loss paths keep explicit UNKNOWN and fail-safe. Linux/macOS/Windows workflows are prepared; only actual runs establish platform evidence. Phones, vehicles, drones and edge accelerators require separate measured device/firmware/calibration/power/latency/controller records.
