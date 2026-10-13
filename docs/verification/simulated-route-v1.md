# Bounded synthetic route evidence v1

P7 simulation only; no physical free-space, dynamic safety, controller or platform
qualification. See [the contract and technology decision](../architecture/simulated-route-v1.md).

Retained RED: initial import failed because `aethron.simulated_route` did not
exist. The resource-probe test then failed with
`TypeError: run() got an unexpected keyword argument 'route'`; the probe now
explicitly selects route mode and checks a 31-cell result on every measured call.

Focused results:

- Ten new route tests pass; the combined P5/P7/adapter suite has 41 passing methods.
- All 16 binary 2x2 maps and all 16 start/goal pairs (256 cases) match independent
  Floyd-Warshall reachability and shortest lengths. Every emitted tiny-grid route
  independently passes the existing P7 path checker.
- A seven-cell detour succeeds where the three-cell straight-line baseline hits
  a blocked cell. A 135-cell corridor returns `path_limit`, never a truncated route.
- Unknown/blocked endpoints, disconnected maps, malformed/oversized inputs,
  prohibited fields, unsupported provenance/frames/clocks, expired/future/replayed
  time, lost diagnostics, mutation isolation and terminal close are covered.
- 64 seeded bounded malformed-byte cases export no path and satisfy P5 response
  schema checks. Ruff, Bandit and nine frozen manifests pass.

Reproduce the bounded maximum-grid sample:

```sh
python3 scripts/simulated_plan_probe.py --route --out build/p6-world/route-resource.json
```

[Raw evidence](simulated-route-resource-v1.json) retains 100 wall samples, a separate
traced-memory pass, source/workload hashes and runtime/platform. Each input is an
explicitly free 16x16 grid from [0,0] to [15,15]; deterministic BFS visits the grid
and yields 31 cells. On Linux/Python 3.13.5, p95 was 2.690ms, maximum 70.797ms,
and traced peak 59824 bytes. The unchanged 100ms p95/32MiB software sample gates
pass. This is not total RSS, a hardware measurement, WCET or a language ranking.

The [default assessment mode](simulated-route-assessment-parity-v1.json) was also
run after extending the probe; its 100-input
workload hash matches the original P7 assessment report and its sample gates pass.
Earlier negative latency evidence, including the world adapter's >100ms maximum,
remains unchanged. Full hosted checks and external qualification are not claimed.

Paths are transient synthetic grid candidates. No real sensor geometry, durable
person identity, target designation, navigation transport or actuation is present.
