# Bounded synthetic route search v1

P7 additive simulation slice, 2026-10-10. Consumes explicit static synthetic free
cells, never inferred free-space or sensor/person locations. No physical frame
conversion, moving-obstacle assurance, pursuit, device transport or actuation.

## Technology decision before implementation

Requirements: portable synchronous Linux/macOS/Windows library, <=8192 byte input,
<=16x16 grid, one start/goal, orthogonal unit-cost moves, <=64 output cells. Closed
admission, deterministic tie-breaking, fail-closed uncertainty and bounded work;
no optimization over dynamics, costs, schedules or multi-agent interactions.
Memory is ephemeral; only fixed diagnostics and time watermarks survive calls.

Compared domain-relevant alternatives without excluding uninstalled toolchains:
[MiniZinc](https://docs.minizinc.dev/en/stable/) and
[SWI-Prolog CLP(FD)](https://www.swi-prolog.org/man/clpfd.html) express finite-domain
constraints and richer optimization, but add solver configuration/search-status
semantics to a tiny unweighted reachability problem. OCaml's typed variants and
Rust's ownership offer static guarantees, while retaining the need for strict
external JSON and the P5/P7 time boundary; a new native/runtime interface has no
measured constraint benefit here. Python's
[deque](https://docs.python.org/3/library/collections.html#collections.deque)
provides approximately constant-time operations at both ends.

**Select Python breadth-first search with deque and the P7 public-byte checker.**
Each cell is discovered at most once, examines at most four neighbors and stores
one parent; [BFS complexity](https://www.boost.org/doc/libs/latest/libs/graph/doc/html/graph/algorithms/traversal/breadth_first_search.html)
is O(V+E), here V<=256 and E<=1024. A* can reduce visits on larger
grids, but requires a heuristic/priority queue and offers no better worst-case
cell bound here. No heuristic or solver tuning is required for BFS shortest paths
on unit-cost edges. This is an explicit algorithm/boundary judgment, not a language
speed ranking. Verify optimal lengths against an independent exhaustive tiny-grid
oracle, every emitted route against P7, and resource samples on a maximum grid.
Reassess for weighted/dynamic/multi-node planning or tighter native deployment.
Software sample budgets remain 100ms p95 and 32MiB traced peak, not a hard deadline.

## Interface and plan

`aethron.simulated_route.SimulationRoute(contract).step(data, *, now_ms)` accepts
exactly the [P7 grid request](simulated-plan-v1.md) metadata and grid, replacing
`path` with `start` and `goal`, each [column,row]. P7 strict scalar/grid/byte bounds
remain in force. Only explicit free cells are traversable. Neighbor order is
right, down, left, up; this fixes tie-breaking. Same-cell start/goal yields a
one-cell route only when free. A shortest route over 64 cells is rejected as
`path_limit`; it is not truncated. Disconnected free endpoints yield `unreachable`;
non-free endpoints yield `endpoint_not_free`. No map/path is retained between calls.

Output: `simulation_route_version=1`, `route_found`, `path`, `reasons`, and the
unchanged P5 `recommendation`. The path is empty on every rejection. `route_found`
means only a discrete route exists under the supplied static simulation grid and
passed P7 admission at the caller's trusted time. It never grants motion authority.
The bounded search produces one candidate, which is passed through the existing
stateful P7 checker before export. A failed search still submits its start cell
for strict time admission, advancing the watermark for a structurally valid
proposal; its non-route result is authoritative and is not exported as success.
Invalid requests feed invalid bytes to the checker. All fixed diagnostics survive
watchdog/invalid admission until fresh input; close clears them and is terminal.
Expiry, clock regression and replay checks remain P5/P7-owned and unchanged.

Implementation plan: failing route/admission/loss/privacy tests, then bounded BFS
and strict adapter; exhaustive 2x2 all-map/all-endpoint shortest-length comparison
with a Floyd-Warshall oracle; independent P7 validation of outputs; focused
lint/security and a source-bound maximum-grid measurement. No real deployment.
The measurement extends the existing Python standard-library probe in the same
process, avoiding an IPC timing boundary; no alternate-runtime speed is claimed.
