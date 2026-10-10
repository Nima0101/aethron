# Local aggregate health: fresh V3 review

Decision: **KEEP the local implementation; RETRACT/CLARIFY its availability,
privacy and technology wording.** Review subject is the committed health library
at `8a0dc57f5417cd4499af690f838944244e65e3c3`, introduced by `28528f4`.
Its SHA-256 is `75e284acbea0193f7499ff4c20d5def7cc0195875855f7e1e13a4c61b609c15d`.
The uncommitted leased projection and P11 fabric remain separate, unreviewed
components. Passing the old public API tests on that working copy does not
approve those additions. No lane completion is claimed.

## Current requirements and technology comparison

The actual boundary is a synchronous Linux library receiving at most 256 bytes
per call, 1..1024 caller-authorized slots, four closed input fields and five
output counters. It retains one immutable report and a replay watermark per
slot. No growing event history, I/O or background worker is needed. Exact integer
types, decoded-key duplicate rejection, exclusive expiry and clock rollback
withdrawal are required. The caller supplies the trusted clock and authorization;
there is no independent availability sensor or remote trust protocol here.

No target CPU, RAM ceiling, sustained arrival rate or processing deadline is
specified. The bounded O(N) scan per call and O(N²) full refresh are real costs.
They cannot be relabeled as hard real-time or five-nines availability. A
standalone deployment or specified deadline would reopen this decision.

Primary sources were consulted again on 2026-10-10; assessments below are
engineering judgments for this boundary, not language performance rankings.

| Candidate | Decisive property and assessment |
| --- | --- |
| Python standard JSON + explicit validation | [Parser hooks](https://docs.python.org/3.13/library/json.html) retain ordered key pairs and distinguish integer and floating values. The maintained parser plus bounded state implements the complete local contract without an application lexer. Defaults alone are insufficient. |
| Rust/Serde native library | [Closed struct fields](https://serde.rs/container-attrs.html) support strict decoding. A typed native core is credible; numeric token behavior, thread synchronization and binding error semantics still need complete parity evidence. No measured full-collector advantage is established here. |
| C# System.Text.Json | [Utf8JsonReader](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-utf8jsonreader) supports token-level reading. Explicit duplicate and numeric checks can preserve the contract. Its different local binding boundary needs verification; it is not disqualified for requiring a service. |
| Erlang/Elixir OTP | [JSON decoder callbacks](https://www.erlang.org/doc/apps/stdlib/json.html) make strict decoding credible. Process supervision is useful for a distributed collector, but this library has no actor or mailbox requirement; adding one introduces queue and stale-response semantics to verify. |
| JavaScript/TypeScript | Rerunning the strict Node candidate proves 22 decoder cases, including decoded-key duplicates. Its additional token parser is a larger application-owned ingress boundary than the Python hooks. The candidate is not a complete collector. |
| Ada/SPARK and Go | The [prior source-bound comparison](fleet-health-technology-audit-v2.md#domain-candidates-and-decisive-properties) remains relevant input: proof-oriented state machines and native managed collectors are credible alternatives. Neither a proof requirement nor a standalone deployment has appeared in the current component contract. Neither was benchmarked here. |

KEEP is justified by maintained strict parser hooks, bounded managed state and a
synchronous local boundary satisfying the specified requirements. It is not
justified by installed tools, prior language use or rewrite cost. Stronger native
typing and proof opportunities are useful, but no evidence here establishes an
end-to-end gain that materially wins for this local contract. This is a scoped
decision under stated requirements, not proof of a universal optimum.

## Findings and executable evidence

The old phrase “reports runtime availability” overstated the implementation.
An arbitrary well-formed local report is accepted without a liveness probe.
The contract now calls these caller-reported software states. The old Go/process
rationale and future implementation checklist have also been replaced.

Counts exclude identifiers but do not provide anonymity. A one-slot fixture
exports running=1, exposing that slot's declared state. At expiry a new snapshot
exports unknown=1 while the old detached dictionary still contains running=1.
This demonstrates why a saved snapshot cannot be treated as a freshness token.
A new collector accepts the same report when supplied a compatible fresh clock:
there is no persisted replay floor. These are explicit boundary limitations,
not evidence to weaken validation or extend lifetimes.

[Fresh results](../verification/fleet-health-review-v3.json) retain the source
digest, 15 committed-module tests, 15 working-copy tests and all 22 Python/Node
decoder outcomes. The unchanged V2 probe format is nested as fresh supporting
evidence, not reused as a V3 completion marker. Default Node object validation
still accepts four forbidden representations. Timing samples and traced memory
are retained without a deadline, throughput or hardware qualification claim.
An initial command omitted `PYTHONPATH` and failed before tests; its corrected
run passed and the setup failure remains recorded.

To reproduce the claim observations against the committed module exported as
`fleet_health.py` in a lane scratch directory:

```python
from fleet_health import FleetHealth

raw = b'{"version":1,"state":"running","emitted_ms":1000,"status_expires_ms":3000}'
fleet = FleetHealth(1)
assert fleet.ingest(0, raw, now_ms=1000)
old = fleet.snapshot(now_ms=1000)
assert old["states"]["running"] == 1
assert fleet.snapshot(now_ms=3000)["states"]["unknown"] == 1
assert old["states"]["running"] == 1
assert FleetHealth(1).ingest(0, raw, now_ms=1000)
```

The decoder reproduction commands remain in the V2 audit; use this review's
subject commit when exporting the module. No production behavior change or
threshold adjustment was necessary for these documentation corrections.

## Integration and review status

Consumers receive local software-state counts only, never authorization,
physical readiness, scene evidence or transport security. This contract supplies
no target designation, autonomous control, person history or peer-owned sensor
fusion. P17/P18 architecture, MLS/CNSA qualification and target-device timing
are not implemented or certified by this review. Insufficient information for
tactical deployment.

The next earliest component is signed policy admission. Persistent floors,
admission orchestration, rollout journals, snapshot plans, signed claims and the
uncommitted P11 work remain pending fresh review.
