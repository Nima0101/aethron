# Synthetic world-to-defensive adapter v1

Technology decision before implementation, 2026-10-10; policy-v2 continuation.
This is a serialized Linux/macOS/Windows simulation library, not a controller.
It consumes bounded v3 bytes and trusted host time; no device SDK, network,
privileged installation, physical transformation or hard-real-time deployment.
The frozen 100-frame/32-object software budgets remain 100ms p95 and 32MiB traced
peak. It must preserve source deadlines and diagnostic failures while exporting
no geometry, IDs, prediction, appearance or history.

Candidates were drawn from verified systems, typed functional state machines,
native ownership and portable admission libraries, without requiring installation:

- [SPARK](https://learn.adacore.com/courses/intro-to-spark/chapters/03_Proof_Of_Program_Integrity.html)
  can prove absence of runtime errors subject to proof assumptions. Proving this
  adapter would still require trusted contracts for the foreign parser/fusion;
  no proof requirement or complete proved sensor stack exists here.
- [OCaml](https://ocaml.org/docs/basic-data-types) offers static variants and
  pattern matching for closed state transitions. A separate runtime would need
  additional clock, ownership and scalar translations at this boundary.
- [Rust](https://doc.rust-lang.org/book/ch04-01-what-is-ownership.html) checks
  ownership statically without garbage collection. It is a strong native
  embedding candidate, but this adapter adds no numerical kernel or native SDK;
  an FFI wrapper would still depend on the same parser and world runtime.
- [Python JSON hooks](https://docs.python.org/3/library/json.html) allow duplicate
  and nonfinite rejection. Plain decoding is insufficient; the existing strict
  v3 parser and P5 admission are mandatory, not bypassed with dictionaries.

**Select Python direct composition.** The decisive correctness advantage for
this small adapter is that the exact admitted byte string enters the existing
WorldModel and the aggregate enters P5 through its public strict byte interface.
No second implementation of fusion or clocks is needed. This is not a speed
comparison, a convenience argument or a future controller-language decision.
Bounded integration tests and a complete-path resource sample must support this
choice; reconsider on a measured budget failure with evidence of an alternative
resolving it, native embedding or a formal-proof requirement.

## Boundary and implementation plan

`aethron.simulation_world.SimulatedWorld(contract)` owns one WorldModel and one
DefensiveSimulation. It admits only synthetic v3 frames whose contract matches
trusted local configuration. Invalid provenance/policy is replaced by invalid
bytes before WorldModel admission, clearing linkage without echo. Coordinate
frame and clock declarations stay mandatory and use P6 quarantine rules.

`step(data, *, now_ms, coordinate_frame, clock_domain)` returns exactly
`simulation_world_version=1`, `quarantined`, `diagnostics` and `recommendation`.
Diagnostics preserve the world's bounded fixed reason codes. Recommendation is
an unchanged [P5 v1 response](simulated-defensive-v1.md), with no motion authority.
No world snapshot or track leaves this adapter. Inputs are synthetic declarations,
never hardware evidence; accepted UNKNOWN is not absence or permission.

For an admitted world scene, the aggregate acquisition time is the **original
frame timestamp**, not processing time. Expiry is the minimum of frame time+100ms
and the world scene deadline (including current support/calibration expiry).
World UNKNOWN stays UNKNOWN even with a coasting prediction. If an aggregate is
already expired, P5 rejects it. Quarantine passes invalid bytes to P5, producing
UNKNOWN and immediate expiry. A watchdog withdraws support from both components;
close is terminal for both. No result cache or unbounded diagnostic log exists.

Plan: first exercise synthetic fusion, deadline translation, provenance rejection,
loss/recovery, malformed bytes, clock/frame regression, close and output mutation
through the real components; observe missing adapter RED. Implement composition,
then run focused tests, lint/security and bounded complete-path measurement.
Do not modify any frozen protocol or implement peer-owned platform adapters.
