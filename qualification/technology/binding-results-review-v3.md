# Artifact measurement result review — 2026-10-10

Baseline: `38d171e05fc3fe409a241c6c2b151f6c0e50dd5c`. This review restarted
at the earliest P4 declaration implementation, reread its schema and artifact
binding contract, and reran their negative controls. No new declaration or
artifact API mismatch was demonstrated. The next correction is in the associated
measurement tool, not in a device or real-time data path.

## Reproduced mismatch and correction

`measure_binding` previously checked only truthy artifact verification and falsy
physical qualification during ten timed calls. It ignored the result of the
eleventh, allocation-traced call. It could emit normal evidence with incorrect
counts, failed declaration checks, wrong report types or unsupported authenticity
claims. Three initial regression methods produced 21 assertion failures and no
errors: 17 timed-report substitutions and four traced-report substitutions.

The tool now compares every returned report with an independently specified
synthetic outcome: two sensors, six synthetic records, four matching distinct
artifacts and 4,194,304 supplied bytes, with no findings or physical/authenticity
approval. The only computed expectation is the exact input-manifest digest.
Keys, containers and scalar types must match, so Boolean/float counts cannot
pass through Python's ordinary numeric equality. Unexpected fields fail too.
Failures raise the fixed `binding_measurement_failed` error before any report
is written. The traced result is retained and checked after tracing stops.

Result checks remain outside both timing and allocation measurements. The traced
call now has a small Python wrapper that retains its report; peak allocation is
still a descriptive Python-allocation observation, not process memory, an
allocation ceiling or a direct historical performance comparison. No thresholds,
production validators, frozen contracts or historical evidence were changed.

## Current technology decision

Constraints: synchronous offline source-checkout API; immutable input bytes;
four preconstructed 1 MiB artifacts; ten untraced calls plus one traced call;
exact result types; no device, network, native ABI, standalone distribution or
hard deadline requirement. The experiment must invoke the actual validator and
observe its Python allocations without claiming instrument authenticity.

| Candidate | Decisive fit and limitation |
|---|---|
| Python native hashing plus in-process measurement | Immutable bytes and native SHA-256 satisfy binding. Direct calls preserve original report types and expose the allocations this experiment intends to observe. Explicit guards are needed around permissive defaults. |
| Node crypto/Buffer and external measurement | A current bounded probe reproduced the same four hashes and mutable-alias/owned-copy behavior. It does not implement the complete validator. External JSON transport changes the measured boundary and loses Python container distinctions. |
| Erlang/Elixir binaries, crypto and JSON | A credible immutable-data alternative for a separately specified service. It would measure BEAM data/runtime behavior; that is a different experiment from tracing this in-process API. |
| C# SHA256/System.Text.Json | Span hashing and explicit JSON value kinds fit a native consumer. An external driver would add transport and cannot observe the current Python allocation trace directly. |
| Rust owned bytes/native hash and typed report | A credible native library boundary with static ownership. Selecting it requires a native deployment constraint or evidence of a material improvement for the whole validator, not a hash-only timing comparison. |

Fresh primary-source checks: [Python hashing](https://docs.python.org/3/library/hashlib.html),
[Python allocation tracing](https://docs.python.org/3.13/library/tracemalloc.html),
[Python JSON conversion](https://docs.python.org/3.13/library/json.html),
[Node buffers](https://nodejs.org/api/buffer.html),
[Erlang crypto](https://www.erlang.org/doc/apps/crypto/crypto.html#hash/2),
[Erlang JSON](https://www.erlang.org/doc/apps/stdlib/json.html),
[C# SHA256](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-10.0)
and [JSON value kinds](https://learn.microsoft.com/en-us/dotnet/api/system.text.json.jsonelement.valuekind?view=net-10.0).
Rust and other earlier candidates remain discovery inputs in
[the earlier comparison](retrospective-v2.md), not newly executed prototypes.

**KEEP Python/native hashing and Python in-process instrumentation; FIX result
admission.** Direct observation of the required API/type/allocation boundary is
the decisive property. Installation, familiarity and rewrite cost are not the
decision. No whole-validator speed ranking was demonstrated. Reopen for a native
ABI, target memory/throughput constraint, authenticated producer contract or
standalone installed tool requirement.

## Evidence and remaining scope

The [retained result](binding-results-review-v3.json) contains source observations,
the current measurements and focused checks. Four regression methods cover the
21 substitutions plus a failure at each of the ten individual timed positions.
The related trace-lifecycle/source-observation run passed 12 methods; declaration,
artifact and artifact-review tests passed 24. This is finite synthetic verification.
Source file hashes are observations, not proof of which code executed.

The review remains incomplete; the next earliest component is campaign coverage
and its comparison tooling. P15 procedure validation, installed-product acceptance
and P19 help checks remain software work in the readiness inventory. Hardware and
customer approval remain external. No physical, real-time, availability, MLS,
CNSA or interoperability certification follows. Insufficient information for
tactical deployment.
