"""Public API and adapters exercised without private helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aethron import evaluate
from aethron.adapters import coarse_cue, depth_patch, envelope, thermal_patch

hot = thermal_patch([80], at_ms=1000, calibration_until_ms=2000)
depth = depth_patch([1], at_ms=1000, calibration_until_ms=2000)
result = evaluate(
    envelope([hot, depth], now_ms=1000, lighting="zero_visible", contract="vehicle_stop")
)
assert result["recommendation"]["action"] == "STOP"
assert [c["state"] for c in result["claims"]] == ["UNKNOWN", "UNKNOWN", "PRESENT", "PRESENT"]
radar = coarse_cue("radar", 0.9, zone="sector_a", at_ms=1000, calibration_until_ms=2000)
result = evaluate(envelope([radar], now_ms=1000, zones=["sector_a"], authorized_obstruction=True))
assert all(c["rect"] is None for c in result["claims"])
print("PASS: public Python consumer, thermal/depth/radar adapter boundary")
