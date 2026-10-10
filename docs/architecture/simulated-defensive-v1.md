# Simulation-only defensive recommendations v1

P5 additive software interface; no controller, actuator transport or motion
authority. Intended consumers include P8 capability adapters and future P7
simulation decisions. This interface accepts aggregate synthetic state only;
it cannot carry boxes, identities, trajectories, device commands or telemetry.

Technology decision before implementation (2026-10-10): requirements are a closed
portable interchange, six bounded input fields, one serialized monotonic stream,
strict rejection and no device runtime. Select JSON Schema 2020-12 for the public
shape and a Python standard-library reference admission implementation. Considered
Ada/SPARK for proof, OCaml for typed state transitions, Rust for native embedding,
C# Native AOT for standalone deployment and TypeScript for browser consumers;
their advantages are documented in the [policy-v2 reassessment](../decisions/0008-world-technology-reassessment-v2.md).
Here dynamic duplicate/type/time validation remains mandatory in every technology.
The reference implementation uses the same bounded byte-admission primitives as
v3, with no added FFI/process boundary or runtime dependency. A future hardware
controller needs a separate technology and safety decision; this is not one.
[JSON Schema](https://json-schema.org/draft/2020-12) expresses closed fields and
enums; [RFC 8259](https://www.rfc-editor.org/info/rfc8259/) defines interchange.
Consumers must additionally implement duplicate-key and cross-field/time checks;
schema validation alone cannot establish freshness or provenance.

`aethron.simulated_safety.DefensiveSimulation(contract)` accepts one configured
v3 contract: `warn`, `vehicle_stop`, `drone_hover`, `drone_land`, `drone_retreat`.
Invalid configuration raises fixed `ValueError("invalid_input")`. Configuration
is trusted local policy and cannot be changed by an input payload.

`step(data, *, now_ms)` takes UTF-8 JSON **bytes**, at most 2048 bytes, depth at
most eight, no duplicate or unknown fields or nonfinite/boolean numbers:

```json
{"version":1,"at_ms":100,"expires_at_ms":200,"evidence":"synthetic","state":"UNKNOWN","clock_domain":"host_monotonic_ms"}
```

All times share the caller's trusted monotonic epoch and v3 53-bit integer bounds.
Timestamp/version tokens must be lexical JSON integers; float-form integers such
as `1.0` are rejected even if a generic JSON Schema validator accepts them.
The input is an upstream aggregate declaration, never verified sensor evidence.
`state` is PRESENT or UNKNOWN, never SAFE/ABSENT. `evidence` must be synthetic;
recorded/live/external-unverified data are rejected. The model creates no geometry,
prediction or track. Maximum age is 100ms. Expiry is exclusive:
`at_ms <= now_ms < expires_at_ms <= at_ms + 200`. Accepted frame times strictly
increase; trusted time cannot regress and its high-water survives rejection.
Out-of-order/future/expired declarations cannot reset those watermarks.
Accepted output expiry is further capped at input `at_ms + 100`; a declaration
cannot extend current support by choosing a larger TTL. At the exact 100ms age
boundary, admission can succeed but the returned snapshot is already expired
under this interface's conservative exclusive-expiry convention.

The output has version 1, `simulation_only=true`, `motion_authority=false`,
`requires_independent_controller=true`, the configured contract and its fixed
defensive action (WARN/STOP/HOVER/LAND/RETREAT). `accepted=true` means only that a
synthetic declaration passed admission. It never authorizes action or implies
absence/safety. The state/evidence of an accepted declaration are preserved.
No evidence means UNKNOWN, including malformed input or unsupported clocks.
Rejection emits `accepted=false`, `state=UNKNOWN`, `evidence=null`, no payload
echo and immediate expiry at the last valid trusted time. Only fixed reason
codes are retained; new valid input replaces them. No per-object history exists.

`watchdog(*, now_ms)` emits UNKNOWN with immediate expiry on acquisition loss.
`close()` permanently closes the instance. Neither method extends old evidence.
Callers must serialize access, call the watchdog on stalls and discard expired
snapshots. A recommendation is descriptive simulator data; do not route its action
string to hardware. There is no arming, navigation, pursuit, speed or actuator API.

The [schema](../../contracts/simulation/defensive-v1.schema.json) contains request
and response definitions. [Vectors](../../contracts/fixtures/simulation/defensive-v1.json)
give portable admission examples. Run
`python3 -m unittest discover -s tests -p test_simulated_safety.py -v`.
