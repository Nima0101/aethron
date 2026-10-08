# Frozen darkness acceptance matrix
Frozen before tuning or implementation. No accuracy tuning is authorized on these fixtures.
D01 daylight/low_light/near_dark/zero_visible: RGB presence and passive depth withdraw outside daylight; thermal/radar/active depth stay eligible, never guaranteed.
D02 thermal-only in zero_visible: anomaly retained, human cue UNKNOWN, degraded explicit.
D03 authorized radar-only zero_visible: coarse occupancy retained, no box/human identity/precise location.
D04 conflicting eligible thermal sensors in zero_visible: thermal UNKNOWN, rectangles absent, fail-safe recommendation.
D05 all darkness-capable sensors invalid/missing: all dependent claims UNKNOWN, zero rectangles, fail-safe.
D06 rectangles allowed only for fresh direct non-human thermal/obstacle evidence, quantized bounded coordinates; stale/occluded/ambiguous/human/radar/behind-wall geometry rejected or suppressed. Renderer must independently expire/clear stale rectangles, including replay of old output.
D07 reproducible demo and public README show all lighting modes, stale rectangle withdrawal, darkness disagreement and coarse human/radar privacy. Synthetic labeling always visible; live demonstration blocked until exact hardware evidence exists.
