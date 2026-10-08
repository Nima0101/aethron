# Additive privacy, misuse and safety review for v3
The owner-authorized amendment allows geometric scene-local continuity. Earlier identity/targeting prohibitions remain. This review extends the frozen threat/privacy models; it does not rewrite them or claim an independent audit.

| Threat/failure | Implemented response and limitation |
|---|---|
| Caller supplies names, embeddings, history, external IDs or pursuit action | Closed schema rejects and clears state, errors never echo payload |
| Same person re-enters after expiry | No retained lookup; new random scene token / track ordinal; no appearance association |
| Cross-camera/location linkage | Explicit scene break clears state; hard lifetime limits; integrator must accurately report scene changes |
| Silent disappearance on darkness | Eligible non-visible supports remain; total loss emits UNKNOWN; acquisition stall requires watchdog |
| Prediction mistaken for measurement | Coasting status UNKNOWN, empty current sources, declining score, explicit non-evidence prediction, expiring snapshot |
| Clock replay, skew or stale calibration | Reject invalid clock order; eligibility deadlines/skew; global expiry cannot exceed track deadline |
| Ambiguous crossing or sensor association | Geometry-only ambiguity withdrawal, no assertion of human identity; misses reported |
| Pixel model spoofing/domain shift | Uncalibrated scores, fixed model hash; recorded false positives/negatives public; field qualification blocked |
| Model substitution or native parser abuse | Exact byte count/hash before native ONNX loader; optional native process needs deployment isolation/time budget |
| Hidden-person geometry via obstruction mode | Separate coarse v2 interface; v3 accepts direct mode only; no raw radar/vital-sign API |
| Malicious downstream storage/controller | No built-in logging/network/actuation; code cannot prevent an altered client from misusing outputs; access/retention/controller policy remains external |
| Native memory remnants | No deliberate archive, reset native input reference; no certified memory-zeroization claim |

Tests cover all15 owner-required temporal cases plus numeric underflow, snapshot expiry, random optimal-assignment oracles, parser/state fuzz, pixel negatives and model tamper. Runtime import policy prohibits network/arbitrary execution loaders; permitted native code is a separately hash-constrained optional component. License audit and Bandit are bounded checks, not a security certification. Independent privacy/safety review remains required.
