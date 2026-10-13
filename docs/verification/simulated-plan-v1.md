# Synthetic path assessment evidence v1

P7 software-only supplied-path assessment. This does not certify path execution,
real free-space, platform dynamics or physical safety. See the
[versioned contract and technology decision](../architecture/simulated-plan-v1.md).

Retained RED: initial tests could not import `aethron.simulated_plan`. After the
first implementation, a targeted counterexample failed:
`AssertionError: 'blocked_cell' not found in ['acquisition_stalled']`.
The fix retains only fixed diagnostic codes across watchdog/invalid admission,
clearing them on fresh admitted proposals. It retains no map, path or identity.

Focused verification:

- 11 P7 tests, including 256 exhaustive two-cell path/grid comparisons against
  an independent 2x2 edge-set oracle, pass. Every blocked/unknown visited cell
  or nonadjacent transition rejects the path. Waiting is allowed.
- Closed fields, ragged/oversized grids, negative/outside/noninteger coordinates,
  oversized paths/bytes, duplicate keys, unsupported provenance/frames/clocks,
  expiry, future/replayed time, close and mutation isolation are covered.
- All five configured defensive contracts preserve their fixed action and
  `motion_authority=false`, including admissible synthetic paths.
- Existing P5/world/temporal and bounded-recommendation focused tests remain
  green: 75 total unittest methods, not 75 independent physical trials.
- Targeted Ruff check/format, Bandit, and nine frozen manifests pass.
- 64 seeded bounded malformed-byte cases fail closed and their recommendations
  satisfy the unchanged P5 response schema; no unexpected exceptions.

Reproduce the bounded maximum-shape resource sample:

```sh
python3 scripts/simulated_plan_probe.py --out build/p6-world/plan-resource.json
```

[Raw evidence](simulated-plan-resource-v1.json) records 100 wall samples, a separate
traced-memory pass, platform/runtime and source/workload hashes. Each input has a
16x16 explicit free-cell grid and 64 alternating adjacent path cells. Acceptance
is checked on every measured call. On Linux/Python 3.13.5, p95 was 0.394ms, max
26.974ms and traced peak 31781 bytes. This fits the predeclared 100ms p95/32MiB
sample gates; it is neither total RSS nor a hardware/WCET guarantee. Prior P6/P5
negative timing evidence remains unchanged. No solver/language speed ranking is
inferred, and no external solver was installed or timed.

No map is derived from perception absence. Route search, continuous swept-volume
checks, dynamics and real controller integration remain outside this component.
Hosted publication checks and external qualification are not claimed here.
