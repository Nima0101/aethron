# Synthetic recorded depth appliance fixture

Original AETHRON GPL-3.0-only software fixture, generated analytically: six 3×3
little-endian unsigned 16-bit depth frames, every value 5000 with scale
0.001 metres/unit; 50 ms acquisition intervals and 1 ms declared uncertainty.
The source/target camera has focal length 2 pixels and centre (1,1); the declared
rig translates +0.5 metres on x. The selected centre sample projects to
(1.2,1.0), camera coordinates (0.5,0,5). Declared error bounds are synthetic.
No real sensor, person, environmental measurement or trained model is included.

`depth.aeraw` uses the bounded binary raw replay format. `sensor.json` binds
its SHA-256 and full provider calibration. `appliance.json` contains the
administrator-local profile, with explicit looping. It is intentionally unsigned;
normal appliance CLI boot rejects it until the installer signs its bundle and
provides the local trust root. It does not bypass appliance integrity checks.

For the complete provisioning contract, signed-run procedure and verification
limits see [sensor appliance integration](../../../docs/engineering/aethron-ecosystem/SENSOR-APPLIANCE.md).
