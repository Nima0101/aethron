# Drone companion operator guide — candidate

A qualified installer provisions persistent companion/payload compute, integrated sensors and a measured power/thermal/mass budget. Payload power starts AETHRON automatically. The ground station, phone, provisioning laptop and radio observation link are optional viewers; local processing does not depend on them.

Check local startup/fault status before an authorized operation. Sensor, timestamp or provider failure means UNKNOWN. AETHRON does not arm, change modes, guide pursuit, drive gimbals or override flight-controller failsafes. Follow the pilot/platform's independent operating procedures, airspace permissions and link-loss rules.

Software boot/offline/recovery tests use an emulated Linux companion with synthetic sensing. Flight hardware, payload endurance, exact SDK access, weather and nonvisible accuracy remain unqualified. No flight or actuator operation was performed.
