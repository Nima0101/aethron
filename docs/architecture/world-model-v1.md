# Bounded world-model boundary v1

This additive software interface composes the [frozen v3 runtime](protocol-v3.md).
Its world is one registered normalized image plane in one active scene. It does
not establish metric world coordinates, free space or physical device accuracy.

`aethron.world.WorldModel.step(data, *, now_ms, coordinate_frame, clock_domain)`
accepts strict v3 JSON bytes. Both metadata arguments are mandatory declarations
from a trusted adapter: `coordinate_frame="registered_image_normalized"` and
`clock_domain="host_monotonic_ms"`. All frame/sensor/calibration timestamps must
already share the trusted host clock epoch. The strings do not prove registration
or synchronization. Raw ROS/system/simulation timestamps and map/odom/body frames
are unsupported. One instance has one upstream scene; scene changes require v3
`scene_break`. Never multiplex cameras into an instance or link instances.

Output is an envelope with `world_model_version=1`, the two supported metadata
labels, `quarantined` boolean, and `scene` containing the unchanged v3 output
shape. Existing evidence labels, sources, uncertainty, recommendation and prediction
labels retain their meanings. No additional identity or historical trajectory is
created. A returned output belongs to the caller and cannot mutate runtime state.

Trusted `now_ms` is an integer in the v3 domain and may stay equal but never
regress. Accepted frame timestamps strictly increase. Both high-water marks
survive scene changes, quarantine, invalid input and watchdog calls. Malformed,
duplicate, stale/future or unsupported input clears all tracks and yields an empty
UNKNOWN scene with a fixed diagnostic code, no echoed payload and no evidence
claim. Previously accepted defensive contract remains in force; before any
accepted input it is `warn`. Recovery requires a valid newer frame in the same
clock epoch and creates new ephemeral IDs. Restarting the clock epoch requires
closing the instance and constructing a new instance, without linking IDs.

`watchdog(*, now_ms)` explicitly signals stalled acquisition: UNKNOWN immediately,
no current sources/range, and only v3-bounded uncertain coasting until expiry.
It retains diagnostic reasons from the last step, so sensor-loss or quarantine
evidence is not erased by a timer call or another rejection. Only fixed runtime
reason codes accumulate, without timestamps or payloads; duplicate codes collapse.
A valid newer step replaces those reasons.
The application must schedule watchdog calls and respect every output deadline;
this library creates no thread/timer and previously returned outputs cannot be
revoked. Invalid watchdog time also quarantines. Rejected time is never emitted:
the empty quarantined scene uses the last trusted high-water time (initially zero)
and expires immediately. Valid quarantine time advances that water mark.

`close()` erases linkage and permanently closes the instance. Subsequent calls
remain quarantined UNKNOWN. There is no persistence, I/O, planner, actuator,
appearance embedding, re-identification, or cross-camera association API.

Resource/uncertainty limits are inherited unchanged: 65536 input bytes, 64
detections, 32 tracks, 100ms current-support age, 50ms support skew, 200ms
prediction horizon, 500ms missed-evidence window, 10s track rotation and 30s
session reset. Quarantine stores no rejected payload. The caller serializes access;
instances are not thread-safe. Through-obstruction remains coarse v2 and is rejected.

Run `python3 -m unittest discover -s tests -p 'test_world*.py' -v` for boundary and
simulation verification. See the [technology decision](../decisions/0007-bounded-world-model.md).
