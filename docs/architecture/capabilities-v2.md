# Current capability matrix — safety/protocol v2
| Evidence | Darkness behavior | Direct person box | Through-obstruction |
|---|---|---|---|
| RGB minimized classification | withdraw outside daylight | allowed when fresh with localization | rejected |
| thermal_person minimized classification | eligible with valid quality/calibration | allowed; human model qualification external | rejected |
| depth_person minimized classification | active depth only; valid quality required | allowed; human classification qualification external | rejected |
| Thermal temperature patch | darkness-independent eligibility | never infers human | rejected |
| Active depth patch | darkness-capable eligibility | obstacle only | rejected |
| Passive depth patch | withdraw outside daylight | obstacle only | rejected |
| Radar | darkness-independent eligibility | unsupported | authorized coarse sector only |

Every row is reference-software behavior, not hardware support. External detector model/data, calibration, sensor-plane registration and quality validation must be supplied and reviewed before physical deployment. No human motion, range or association API is implemented; these optional fields are deliberately excluded. Phones/Linux/vehicle/drone remain architecture targets until their CI and HIL evidence passes. Synthetic direct human boxes are now included in the public demo; live boxes remain blocked.
