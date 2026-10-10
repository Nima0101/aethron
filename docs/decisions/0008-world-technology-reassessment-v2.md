# ADR 0008 — retrospective world-lane technology reassessment

2026-10-10. Audit policy version **2**. Audited through `33c4e53` and the
accompanying executable resource probe. This reassessment replaces reliance on
ADR 0007's original candidate shortlist; it changes no frozen protocol or threshold.

## Inventory and requirements, before technology selection

Walked the lane history from its protected-main base through `33c4e53`: the only
lane-built production component is `aethron/world.py`; the other substantial
implementation is its boundary/simulation suite. Also reviewed the inherited
recommendation and temporal-fusion dependencies below so their language is not
silently grandfathered. No P5 controller, P7 planner, P9 digital twin or P10
coordination engine has been implemented by this lane yet.

Deployment: a synchronous portable library consuming v3 bytes, currently on
Linux/macOS/Windows, Python 3.9+, with versioned JSON available to foreign clients.
Python API compatibility is a consumer contract, not a requirement that internals
remain Python: native internals with a wrapper were considered. No privileged
runtime, network service, actuator, device SDK, GPU, physical calibration or
hard-real-time claim is needed. Operations are serialized and memory-only.

Required properties: strict duplicate/nonfinite/type rejection before state use;
53-bit interoperable integer timestamps; no unsupported clock/frame conversion;
bounded diagnostics and ephemeral state; current-evidence provenance and uncertainty;
no unsafe deserialization. Frozen maxima remain 64 detections, 32 tracks, 100ms
software p95 and 32MiB traced peak. A measured sample is not WCET or total RSS.
Lower resource use is useful, but correctness, the number of distinct admission
boundaries, and meeting these limits take priority over unconstrained throughput.

## Open candidate discovery and decisive properties

Candidates came from verified systems, typed state machines, portable native
deployment and numerical simulation ecosystems, including uninstalled toolchains.
Availability, familiarity and rewrite cost did not eliminate any candidate.

| Candidate | Source-bound capability | Consequence for these components |
| --- | --- | --- |
| Ada/SPARK | [SPARK assurance levels](https://docs.adacore.com/spark2014-docs/html/ug/en/usage_scenarios.html) include proofs of integrity properties and absence of many runtime errors, with explicit exclusions and subset restrictions. | Strongest candidate if proof becomes a requirement. A proof of an isolated guard does not prove an unanalyzed foreign fusion/parser call; a full proof boundary would need explicit contracts for those calls. No such proof or certification is claimed here. |
| OCaml | [Pattern matching](https://ocaml.org/manual/5.3/patterns.html) and [compiler diagnostics](https://ocaml.org/manual/5.5/comp.html) support typed variants and incomplete-match detection. | Credible memory-safe state-machine implementation. External JSON still needs closed-schema and numeric validation; wrapping the existing runtime adds a second managed runtime/translation boundary. Static exhaustiveness is a benefit, not end-to-end validation. |
| Rust | [Ownership](https://doc.rust-lang.org/book/ch04-01-what-is-ownership.html) provides memory-safety guarantees without GC; [Serde](https://serde.rs/) supports typed serialization. | Credible native library candidate for strict deployment budgets. A wrapper must handle foreign ownership, exceptions/panics and every v3 scalar/provenance field, or move the whole runtime behind the public contract. No native implementation was benchmarked, so no comparative speed claim is made. |
| C# Native AOT | [.NET Native AOT](https://learn.microsoft.com/en-us/dotnet/core/deploying/native-aot/) compiles ahead of time into platform-specific artifacts and has deployment restrictions. | Credible typed standalone service/library; avoids JIT at deployment. A native wrapper or separate process adds an independently validated boundary for the current in-process consumer API. AOT alone does not establish a deadline or correct JSON admission. |
| Julia / PackageCompiler | [PackageCompiler](https://julialang.github.io/PackageCompiler.jl/stable/) supports sysimages, apps and libraries, using ahead-of-time work to reduce compilation latency. | Serious numerical/simulation candidate. Current estimation is bounded two-state scalar filtering and small assignment, with no large dense solver or training workload that would justify a new numerical runtime on measured requirements. Julia has not been timed here. |
| TypeScript / Node.js | [Narrowing](https://www.typescriptlang.org/docs/handbook/2/narrowing.html) supports discriminated unions; [Node test runner](https://nodejs.org/api/test.html) supplies isolated tests. | Credible portable consumer and contract-test implementation. Static types do not validate incoming bytes. A JSON/IPC adapter cannot directly test Python object aliasing, bool-versus-int calls, or exact exception behavior; those require an additional in-process test layer. |
| Python / standard library | [JSON hooks](https://docs.python.org/3/library/json.html) expose ordered object pairs and nonfinite constants; [unittest](https://docs.python.org/3/library/unittest.html) supports direct API/exception tests. | Explicit guards are still essential; plain `json.loads` is insufficient. Current bounded parser and same-process state calls avoid an extra native ownership or IPC failure boundary. Tests exercise those guards and live mutation isolation directly. |

## Executable comparison and negative evidence

New command: `python3 scripts/world_technology_probe.py`. It uses the exact fixed
100-frame/32-object workload from the frozen temporal benchmark. It compares the
full current WorldModel against direct Session, checks every output retains 32
current observations, measures wall time without tracing, then runs a separate
memory pass. It writes raw samples, workload/source hashes and failure status
before returning failure for a budget miss. This is a same-runtime baseline
comparison, **not** a cross-language benchmark.

The [retained report](../verification/world-technology-policy-v2.json) on Linux
x86_64 / Python 3.13.5 measured:

| Component path | p50 ms | p95 ms | max ms | Traced peak bytes |
| --- | ---: | ---: | ---: | ---: |
| Direct Session | 3.116 | 65.946 | 83.928 | 122822 |
| WorldModel | 4.240 | 65.767 | 78.701 | 144523 |

Both samples fit the frozen budgets. CPU p95 is reported only diagnostically;
wall tails remain material and no scheduler cause or speedup is inferred. The
earlier [negative timing measurements](../verification/world-model-v1.md) remain
published. A single positive sample does not qualify hardware or erase a failure.

Tests verify the reporting boundary rejects incomplete/nonfinite measurements and
does not round an over-budget result into a pass. Initial RED was the missing
`scripts.world_technology_probe` module. The runtime decision also requires the
18 world tests, 21 inherited temporal tests and bounded-recommendation test to pass.

## Ordered decisions

1. **Inherited recommendation mapping — KEEP Python.** A five-contract, bounded
   enum-to-recommendation mapping has no planner, controller or numerical kernel.
   Closed admission plus exhaustive contract tests is directly observable.
   SPARK/OCaml can improve static assurance, but a foreign wrapper adds another
   failure boundary without proving the originating evidence or authorizing
   actuation. Select the direct checked mapping for the present advisory API;
   do not treat it as a future controller-language decision.
2. **Inherited v3 fusion/association/state estimation — KEEP Python.** Current
   strict parser, small scalar state, expiry/privacy tests and measured full-path
   resource headroom satisfy this portable software interface. Julia/native
   implementations may be faster; no measured required throughput, dense-matrix
   operation, no-GC deadline or proof requirement establishes a material win here.
   The selected implementation has one schema/admission implementation and no
   new native ownership surface. This is not a ban on a later native kernel.
3. **P6 WorldModel — KEEP Python.** Preserve the versioned envelope and direct
   synchronous state-reset semantics. The complete boundary fits the resource
   sample and passes malformed input, high-water, evidence-loss and mutation tests.
   A typed foreign guard would still depend on the unchanged parser and Session;
   its type guarantees do not remove that trust boundary. Adding FFI/IPC without
   an evidenced constraint win increases independently checked conversions and
   failure modes. This correctness tradeoff, rather than prior implementation
   investment, is decisive.
4. **Boundary/simulation tests and new measurement tool — KEEP Python unittest
   and standard-library instrumentation.** Direct calls test invalid Python
   scalar types, reference isolation and exceptions that serialization can erase.
   Node or Julia runners are credible for portable JSON fixtures; replacing these
   in-process tests would lose coverage or require a second interpreter bridge.
   The measurement tool records the executed runtime directly and has no product
   dependency. It uses no solver, training engine or statistical approximation.

All decisions are evidenced KEEP; no winning migration remains deferred. These are
scope-specific judgments, not a claim that Python wins all performance or safety
comparisons. Reopen the relevant component on native embedding, formal assurance,
parallel processing, tighter memory/latency requirements, or a reproducible budget
failure with evidence that an alternative resolves it. Future P5/P7/P9/P10 work
must make its own current technology decision before implementation.
