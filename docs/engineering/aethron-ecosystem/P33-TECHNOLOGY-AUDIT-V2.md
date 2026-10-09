# P3.3 retrospective technology reassessment, policy 2

Review baseline: `20d54aeaaca1d20078112335d5dd12a2d5acdcc3`.
This supersedes earlier technology-selection notes for the components reviewed
below. It is an incomplete audit, not a P3.3 or P12 completion claim.

## Inventory and cursor

Review the original client boundary before its later lifecycle changes. The
substantial implemented P3.3 surface is `examples/clients/typescript`: generated
API types/schema, runtime validation, observation projection, HTTP/SSE lifecycle,
and packed distribution with synthetic fixtures. No separate Android/JVM client,
desktop launcher, or P12 scene/map/mission/replay application was found at this
baseline. Their absence is outstanding software work, not an external gate.

| Component, in dependency/history order | Policy-2 status |
| --- | --- |
| Versioned contract consumption and runtime admission | MIGRATE to generated AJV validators; executable evidence below |
| Observation ownership, clocks and projection | Pending reassessment; existing regression suite retained |
| Authenticated stream/session/renderer lifecycle | Pending reassessment; existing regression suite retained |
| Package distribution and contract fixture tooling | Pending reassessment; migration package verification below is a regression check |

P1.5 supplies `scripts/edge_generate_types.py`, `scripts/edge_node_e2e.py` and
`integrations/edge/aethron_edge/client.py`. They are shared foundation interfaces,
not new implementations owned exclusively by this lane. Their policy-2 producer
audit must be reconciled with the foundation lane; no competing generator or
Python observer was created here. The web camera detector is not a P12 operator
application. Appliance supervision/provisioning belongs to its producing lanes.
These boundaries do not certify those components or exempt their consumers from
the remaining audit.

## First component: contract consumption and runtime admission

Constraints: an installable Node 22 ESM client with TypeScript declarations must
accept untrusted JavaScript values against the existing API-v1 JSON Schema,
including strict additional-property rejection, finite numbers, bounded integers,
enums and Unicode lengths. Admission must not coerce or mutate input. Preserve
scene/health/gap semantics and UNKNOWN current state. No native device API,
heavy numerical kernel or real-time qualification is involved. Startup memory,
dynamic-code exposure, interoperable packaging and reproducibility matter.

The language search included credible source-to-JavaScript and WebAssembly
ecosystems, not just installed compilers. Primary documentation consulted
2026-10-10:

| Candidate | Decisive properties for this boundary |
| --- | --- |
| TypeScript / native ECMAScript | [Declarations describe the JS package interface](https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html). They do not validate incoming values. Generated JS validators directly consume JS objects and can run under the host's dynamic-code restriction. |
| ReScript | [genType exports values and types to JS/TS](https://www.rescript-lang.org/syntax-lookup/decorator_gentype/). Its stronger internal types are credible, but external unknown JSON still requires a decoder or schema-validator binding. No demonstrated improvement in the versioned admission decisions. |
| Kotlin/JS | [JS export and type mappings](https://kotlinlang.org/docs/js-to-kotlin-interop.html) make JS library delivery feasible. Export restrictions and JS interop remain part of the boundary; internal Kotlin types alone do not check arbitrary JS objects. No JVM/Android code is shared by this implemented component. |
| Dart compiled to JS | [Static JS interop declarations](https://dart.dev/interop/js-interop/usage) support host integration. This boundary would still require runtime schema admission plus an exported JS interface; no measured numerical workload favors the extra compilation layer here. |
| Rust / WebAssembly | [Reference types reduce JS/Wasm glue](https://wasm-bindgen.github.io/wasm-bindgen/reference/reference-types.html). Native memory guarantees are useful for native kernels; this client receives JS values and uses host networking. Either schema validation stays in JS or moves across an additional data boundary. No native kernel advantage is established for this component. |

Decision: **KEEP TypeScript/ECMAScript for the public boundary; MIGRATE validation
from import-time compilation to generated validators.** This is based on direct
host-value admission, schema fidelity and the measured runtime strategy below,
not compiler availability or rewrite cost. Other-language prototypes were not
executed; no comparative speed/memory ranking of those languages is claimed.
Revisit if a required native kernel or shared JVM implementation changes the
constraints. Pending components must receive their own decisions.

[AJV standalone generation](https://ajv.js.org/standalone.html) supports compiling
schemas during builds and avoids runtime Function construction. The production
build now generates CJS validators and the ESM client imports them. Keep strict
AJV 8.20.0 and the exact schema; no alternate handwritten schema or type-only
decoder is introduced. CJS accommodates the generated Unicode-length `require`
helper. AJV therefore remains a runtime dependency. The generated module adds
74,916 uncompressed bytes; this migration does not claim a dependency-free or
smaller package.

## Executable evidence and limitations

The pre-migration client failed to import under
`--disallow-code-generation-from-strings`; the migrated client passes. All 35
observation/transport regressions also run with that restriction. The additional
validation tests compare both old and new validators on 682 cases, including
nested deletions/replacements, non-finite numbers, unknown fields and Unicode
boundaries. Input mutation is checked. A deterministic regeneration comparison
binds built code to the bundled schema. This is same-compiler migration parity,
not an independent proof that the upstream schema captures all safety semantics.

`node audit-validation.mjs` executes three sequential cold processes per strategy,
alternates order and performs 10,000 alternating valid/invalid scene validations
per process. The median validator-ready interval fell from 1,859.77 ms to
110.95 ms on the shared Linux Node 22.23.2 host; raw results include RSS deltas
and warm-loop timings. The clock excludes process launch and fixture setup.
Scheduling pressure makes these observations unsuitable as frozen thresholds or
platform-performance claims. Dynamic-code exclusion and unchanged admission are
the decisive checks. Source hashes and all results are in the
[evidence record](evidence/phase3/p33-validation-audit-v2.json).

Retained failures: the original dynamic-code import failure; a test authoring
error that applied the track-ID length constraint to `reasons` (both validators
agreed; corrected test, unchanged schema); host thread-allocation failures during
the first combined verification/probe attempt; and an initial npm pack failure
using the read-only default cache. Focused checks were rerun sequentially with
bounded Node resources and a workspace cache. No full repository, VM, Docker,
device, browser or live-server qualification is claimed.
