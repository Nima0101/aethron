# Aggregate health: retrospective technology audit, policy v2

Decision: **KEEP Python 3 standard-library implementation for the bounded local
health library.** This decision covers the component introduced by `28528f4`, at
source revision `a8276225c0da9952a2629a704be3b42bb4614fd7`. It supersedes the earlier
technology paragraph in `fleet-health-v1.md`; that paragraph alone was insufficient.
It does not decide the technology for fleet authentication, persistence, rollout
or distributed fabric. Those components remain subject to separate retrospective
review. No migration is required for this component by this decision.

## Constraints established before comparison

- Linux local control-plane library, called synchronously by an appliance
  supervisor. Preserve the public JSON contract and fail-closed errors when
  replacing the implementation. A native library with a binding is a valid
  alternative; other languages do **not** inherently require a network service.
- One authorized table of 1..1024 slots, one report and replay watermark per slot,
  input at most 256 bytes, five output counters, no growing history or labels.
- Strict UTF-8, duplicate-field rejection (including escaped duplicates), closed
  fields, integer tokens distinct from floating-point tokens and booleans,
  exclusive expiry, and retained replay floors after invalidation.
- Shared callers require serialized updates and detached snapshots. No socket,
  database, background thread, SDK, OEM library or actuator is required.
- The 2000 ms freshness ceiling is a validity rule, **not** a processing deadline.
  No hard real-time latency, appliance RAM budget, measured arrival rate or
  hardware certification has been supplied. Do not invent one to choose a winner.
- Prefer memory-safe application code and a small independently reviewable input
  boundary. Deployment and maintenance include the decoder, clock/locking
  semantics and any binding, not just the counter loop. Installed tools and
  familiarity receive no selection weight.

## Domain candidates and decisive properties

Primary sources were consulted on 2026-10-10. The assessment column is an
engineering inference from those sources and the executable probes below.

| Candidate | Source-bound capability | Assessment for this component |
| --- | --- | --- |
| CPython with standard `json` | The decoder distinguishes integer/float values and exposes ordered object pairs and nonfinite-number hooks. Defaults alone permit duplicate fields and nonfinite values. [Python 3.13 JSON](https://docs.python.org/3.13/library/json.html) | Closed validation can use the maintained parser without implementing a JSON lexer. Application state uses bounded managed objects and an explicit lock. Runtime checks remain necessary; the interpreter and its native parser are trusted dependencies. |
| Rust with Serde | Ownership provides compile-time memory management; Serde supports rejecting unknown fields, and JSON numbers expose integer checks. [Ownership](https://doc.rust-lang.org/book/ch04-01-what-is-ownership.html), [Serde attributes](https://serde.rs/container-attrs.html), [JSON numbers](https://docs.rs/serde_json/latest/serde_json/struct.Number.html) | Strongest native-library alternative: fixed arrays, typed state and no tracing GC. Full input rejection, synchronization and binding semantics still need tests. No Rust latency/RSS result is claimed here. Native speed and static type advantages are real design benefits, but have not exposed a missing requirement in this bounded local interface. |
| C# with System.Text.Json / Native AOT | `Utf8JsonReader` is a low-allocation forward reader; Native AOT can deploy native code without a separately installed .NET runtime. [Reader](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-utf8jsonreader), [AOT](https://learn.microsoft.com/en-us/dotnet/core/deploying/native-aot/) | Credible memory-safe native deployment. Token inspection and duplicate tracking can implement this contract without losing numeric spelling. A binding and its ownership/error conventions would still be part of the local library. No unsupported claim that .NET necessarily requires a separate service or JIT. |
| Erlang/Elixir on BEAM | OTP JSON supplies object and numeric decoder callbacks. Process isolation comes with message-copying and mailbox considerations. [OTP JSON](https://www.erlang.org/doc/apps/stdlib/json.html), [Process costs](https://www.erlang.org/doc/system/eff_guide_processes.html) | Well matched to independently supervised network collectors; no such actor/service requirement exists here. A mailbox would need explicit bounds and stale-response rejection in addition to the current synchronous contract. JSON callbacks make strict decoding credible; BEAM is not rejected for lack of an installed toolchain. |
| Ada/SPARK | GNATprove can establish absence of run-time errors under proof assumptions; guarantees do not automatically extend to unproved callees. [SPARK proof scope](https://docs.adacore.com/spark2014-docs/html/ug/en/usage_scenarios.html) | Attractive when proof of the state machine is required. A proved counter core alone would not prove the UTF-8/JSON boundary, clock source or binding. This non-qualified reporting library has no supplied formal-assurance obligation; a partial proof is not a material end-to-end assurance gain by itself. |
| Go with JSON token decoding | Current JSON documentation explicitly distinguishes v1/v2 duplicate and invalid-UTF-8 behavior. [Go JSON](https://pkg.go.dev/encoding/json) | Viable standalone collector. Pin the API/version and validate exact integer tokens; do not assume map decoding preserves duplicates. For a local binding, scheduling and lifetime conventions also enter the boundary. No Go performance result is claimed. |
| JavaScript/TypeScript on Node | Standard JSON parsing builds language values; duplicate property occurrences and original numeric forms cannot be recovered from the final plain object alone. [ECMAScript JSON.parse](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.parse) | Executable comparison below. A strict decoder is possible, but the prototype needs a bounded token parser in addition to `JSON.parse`. TypeScript types alone would not validate these runtime bytes. No claim that JavaScript cannot satisfy the protocol. |

## Executable evidence

The checked-in [probe](../../scripts/technology-audit/fleet_health_probe.py) and
[Node candidate](../../scripts/technology-audit/fleet_health_decoder.mjs) evaluate
22 byte-level cases. The Node implementation is an **audit-only decoder** for
this flat schema, not an alternate production collector. It includes strict
UTF-8, a size bound, token preservation and decoded-key duplicate detection.
Both strict decoders passed all 22 cases. Default Node object validation wrongly
accepted duplicate keys, escaped duplicates, `version: 1.0` and exponent-form
time. Deliberately substituting that relaxed result into the probe failed with
`candidate_contract_failure`. The candidate therefore demonstrates a real
contract-preserving option, rather than disqualifying a language using defaults.

The committed Python implementation also passed its 15 existing health tests,
including expiry, replay, clock regression, privacy and 257 deterministic hostile
byte inputs. Calls use an explicit lock; these tests do not measure thread
contention or prove the lock implementation.

[Measured output](../verification/fleet-health-technology-audit-v2.json) records
source SHA-256, environment, individual samples and earlier-run evidence.
On the shared Linux x86-64 host, the retained traced allocation for a fully
populated table was 227,079 bytes (peak 229,045). Five fresh 1024-report sweeps
including a snapshot took about 201..278 ms; snapshot sample means were about
413..564 microseconds. The decoder timing samples varied substantially between
runs and within each run. **These results do not rank language speed, establish
a worst-case execution time, or qualify a deployment rate.** The 2000 ms validity
window must not be turned into a benchmark pass threshold. Process RSS includes
probe/runtime overhead and is not a like-for-like memory ranking.

No Rust, .NET, BEAM, SPARK or Go executable benchmark was run. Their capabilities
were compared from primary sources; this limitation is not evidence against them.
The Node probe does not establish full collector parity or production readiness.

## Decision rationale and reopening conditions

Python is retained because this particular component can express the complete
strict input boundary using maintained parser hooks, fixed managed state and
synchronous locking, with no application-owned lexer, asynchronous queue or
foreign binding. The bounded measurements demonstrate an executable small-table
implementation; the negative contract tests demonstrate why a superficially
shorter decoder is insufficient. A fresh implementation with the same local
call boundary would receive the same recommendation.

Rust is the closest alternative and supplies stronger static state/ownership
checking. C# and BEAM also offer viable safe decoders; SPARK offers stronger proof
possibilities. None of those strengths currently resolves an established missing
requirement that outweighs the additional integration boundary for this local
library. This is a scoped maintainability/security decision, **not** a claim that
Python is fastest, universally best, or entitled to remain because it exists.
Rewrite effort and available compilers are not reasons for KEEP.

The O(N) scan on each ingest means a full refresh is O(N²); N is capped at 1024.
The measurement preserves that cost rather than hiding it. Reopen the decision
before increasing capacity, specifying sustained ingest/deadline requirements,
shipping a standalone collector, removing the caller's interpreter, or requiring
formal assurance. Native full-state-machine prototypes and contention testing
would then be necessary. No current timing evidence authorizes a production
frequency or hardware claim.

## Reproduce the bounded audit

Use a scratch directory within this lane. Export the committed file so unfinished
health extensions cannot silently change the subject. With that directory in
`$audit_dir`:

```sh
git show a8276225c0da9952a2629a704be3b42bb4614fd7:integrations/edge/aethron_edge/runtime/fleet_health.py > "$audit_dir/fleet_health.py"
python3 scripts/technology-audit/fleet_health_probe.py --vectors-only > "$audit_dir/vectors.json"
node scripts/technology-audit/fleet_health_decoder.mjs < "$audit_dir/vectors.json" > "$audit_dir/node.json"
python3 scripts/technology-audit/fleet_health_probe.py --module "$audit_dir/fleet_health.py" --candidate "$audit_dir/node.json"
```

Timing values are observations and will vary. The source digest and boolean
contract outcomes are the reproducible evidence. Tools run only local synthetic
code; no network, vehicle, installer or remote command is exercised.
