# Synthetic path assessment v1

P7 bounded software slice, 2026-10-10. No route generation, robot transport,
physical map conversion, person tracking or actuation. A positive assessment
means only that the supplied discrete path fits a supplied static synthetic grid.
It is not a safe-motion claim. The defensive P5 recommendation remains present
and never grants motion authority, even when the path passes.

## Requirements and technology selection before implementation

Deployment is a synchronous Linux/macOS/Windows library, memory-only, one serialized
stream. Inputs are closed JSON bytes <=8192 bytes, depth <=8; grids <=16 by 16,
paths <=64 cells. No external solver/service, native device SDK or proof/hard-time
requirement. Bounds are fixed for this new v1 contract before evaluation; existing
v3/P5 limits are unchanged. One call inspects at most 256 cells and 64 path entries.
Strict ingress, original-time expiry, deterministic decisions and reviewable
failure reasons outrank unconstrained search throughput.

Considered current domain-relevant options including uninstalled ecosystems:

| Candidate | Evidence and decisive fit |
| --- | --- |
| MiniZinc | [Handbook](https://docs.minizinc.dev/en/stable/) describes solver-independent constraint/optimization models. Strong candidate for future constrained route search; this fully supplied path has no unknown variables or optimization objective. Solver search/configuration adds a termination and result-translation surface without helping this linear check. |
| SWI-Prolog CLP(FD) | [Manual](https://www.swi-prolog.org/man/clpfd.html) provides finite-domain constraints and relational queries. Useful for generating alternatives, but no domain search is required here; it would still need strict JSON and trusted-time admission. |
| OCaml | [Typed data and pattern matching](https://ocaml.org/docs/basic-data-types) express closed cell/state variants. A strong standalone checker candidate, with a second managed-runtime boundary if composed with the current P5 byte API. Static types do not by themselves check external bytes. |
| Rust | [Ownership](https://doc.rust-lang.org/book/ch04-01-what-is-ownership.html) supports native memory safety without GC. Relevant to a future embedded validator; no native deployment/WCET requirement exists for this simulation checker. Cross-runtime P5 ownership and exception conversion would remain additional boundaries. |
| Python standard library | [JSON hooks](https://docs.python.org/3/library/json.html) permit strict duplicate and nonfinite rejection. Direct P5 public-byte admission preserves its tested replay/clock/expiry state machine, and explicit loops have bounded work with no solver search. |

**Select Python with direct bounded checks and P5 admission.** This is a judgment
about explicit linear work and avoiding a second clock/admission implementation,
not existing language preference, tooling availability or a cross-language speed
claim. Compare the path algorithm exhaustively against an independent tiny-grid
oracle and record a bounded maximum-shape resource sample. Reassess for actual
route optimization, native embedding, proof requirements or failed budgets.
The measurement uses Python's standard-library clocks/tracemalloc in the measured
runtime, avoiding an IPC timing boundary. Its predeclared sample gates are the
existing software limits: 100ms p95 and 32MiB traced peak, not a hard deadline.

## Versioned interface

`aethron.simulated_plan.SimulationPlan(contract).step(data, *, now_ms)` accepts:

```json
{"version":1,"at_ms":0,"expires_at_ms":100,"evidence":"synthetic","coordinate_frame":"synthetic_grid","clock_domain":"host_monotonic_ms","grid":[["free","free"],["unknown","blocked"]],"path":[[0,0],[1,0]]}
```

All fields are mandatory; extras, duplicates, float/bool integer tokens,
nonfinite numbers, unsupported evidence/frame/clock and malformed/ragged grids
are rejected. Rows and columns each range 1..16; cells are free/blocked/unknown.
Path length is 1..64; each coordinate is a two-integer [column,row] inside the
grid. Consecutive cells must be equal (wait) or orthogonally adjacent; no diagonal
or jump. Every visited cell must explicitly be free. Unknown is not free-space.
No coordinates are projected from P6 registered image geometry. Synthetic free
cells must be supplied by a simulation scenario, never inferred from absent
tracks. Footprint is one grid cell; no speed, dynamics, swept-volume or moving
obstacle safety is asserted.

P5 controls strict increasing frame times, nonregressing trusted time, age <=100ms,
exclusive expiry and expiry cap at acquisition+100ms. Consumed, structurally valid
but infeasible proposals advance the same watermark; replay cannot reset it.
Invalid input feeds rejection through P5, so known P5 faults remain bounded and
no proposal bytes are echoed. Successful fresh admission clears prior faults.

Output fields are `simulation_plan_version=1`, `input_accepted`,
`plan_admissible`, `reasons`, and `recommendation` (the unchanged P5 v1 response).
`input_accepted` means strict admission/time checks passed, not path feasibility.
`plan_admissible` also requires no blocked/unknown cell or invalid transition.
No path, grid or identifier is returned or retained. Reason codes are fixed,
deduplicated and sorted. Watchdog/close emit non-admissible UNKNOWN with immediate
expiry through P5. Returned output is detached. Caller must serialize access and
expire snapshots. No action string is routed to a device.
Known fixed path failures survive watchdogs and malformed/time-rejected input
until fresh valid admission replaces them. No grid/path history is retained;
close erases previous diagnostics and is terminal. At the exact P5 capped expiry,
`input_accepted` can be true but `plan_admissible` is false (`expired_snapshot`).

Plan: RED admission, timing, geometry, privacy and lifecycle tests; implement the
linear checker; exhaustive 2x2 path parity; targeted lint/security and resource
sample; publish a separate small commit. The broader P7 planner remains future
work and cannot use this result as authority for real motion.
