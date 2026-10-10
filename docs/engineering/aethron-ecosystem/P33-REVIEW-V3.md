# P3.3 client review, revision 3

Baseline: `0310a092bf45334f1b94ae2855ef032d3705073c`, including the pending
cancellation correction. This starts a fresh review; earlier audit evidence is
retained and does not establish completion. Scope is the read-only Node client
and its distribution boundary. No iOS implementation is included.

## First component: generated contract admission

Requirements: consume the versioned JSON schema without coercion or hidden
mutation; reject unsupported fields, unsafe numeric values and false authority;
provide a Node ESM interface and TypeScript declarations; avoid runtime schema
compilation. Neither schema admission nor a bearer token attests sensor accuracy,
transit freshness, a deployment authorization policy or hardware qualification.

Reviewed generator, bundled schema, declarations, package configuration and
validation tests. Current source research (2026-10-10) revisits the candidate set:

| Candidate | Evidence and decision for this component |
| --- | --- |
| TypeScript/ECMAScript with generated AJV | [Standalone generation](https://ajv.js.org/standalone.html) separates compilation from runtime validation. The current build demonstrably produces identical validators and imports with string code generation disabled. KEEP. |
| ReScript | [JSON decoding](https://rescript-lang.org/docs/manual/latest/json) provides explicit typed boundary handling. For this schema-owned contract a handwritten decoder would add a second definition; binding the same generated validator would preserve the existing runtime mechanism. No additional internal state machine in this component benefits from that change. |
| Kotlin/JS | [JavaScript exports and type mapping](https://kotlinlang.org/docs/js-to-kotlin-interop.html) make it a credible library implementation. Exported static types still require runtime admission, and no shared Kotlin domain implementation is present here. It offers no demonstrated replacement for schema validation. |
| Dart/JS | [Host interop](https://dart.dev/interop/js-interop/usage) supports a compiled client, but external declarations are not the versioned schema's runtime validator. An additional JS interface would still be needed for the selected public package contract. |

**KEEP the language and generated-validator strategy; FIX the evidence gap.**
The earlier 682-case test compares two implementations using the same AJV engine.
That establishes migration parity, not independent correctness. Fourteen new
explicit negative cases now reject authority escalation, identity/embedding
fields, prediction-as-evidence, nonfinite covariance, unsafe/boolean counters,
lease overflow/coercion, extra tracks and PRESENT health messages. Both checks
are retained. No foreign-runtime speed ranking is claimed. Current decisive
properties are direct host-value validation and one authoritative schema, not
installed tooling or familiarity. No new production migration is justified by
these checks.

The current source and tests contain no actuator transport. This consumer exposes
UNKNOWN current state and does not provide a command interface. Its checks are
not MLS, CNSA, DDS, hard-real-time, five-nines, or tactical deployment certification.
Any such downstream interpretation is unsupported. The producer owns changes to
its versioned schema; this review does not rewrite that peer interface.

## Review cursor and pending work

| Owned surface | Fresh review status |
| --- | --- |
| Generated contract admission | Reviewed above; 4 validation tests pass, including 14 independent negative cases |
| Observation projection and local clocks | Next earliest component; previous private-field/timing evidence is input only |
| HTTP/session/stream/renderer lifecycle | Pending full V3 review; in-flight cancellation safety fix retained with four RED-to-GREEN regressions |
| Package distribution and fixtures | Pending full review; focused installed-artifact checks are regression evidence only |
| Android/JVM, desktop lifecycle, P12 operator application | No completed implementation identified in the previous inventory; fresh inventory and justified implementation decisions remain outstanding |

No completion marker is created. Session-response limits, lexical integer-form
admission and producer whole-event versus payload-size reconciliation remain
known open issues. Cancellation no longer blocks DELETE, but a source may ignore
cancellation and a remote server may fail to delete its session. Full live-server,
platform and deployment qualification are not established by synthetic tests.
