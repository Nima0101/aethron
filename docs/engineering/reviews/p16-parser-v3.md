# P16 parser review v3

Review baseline: `d896e547da2ed0e62d086ab1829b52446a8a67d7`.
Decision: **FIX integer token admission; KEEP bounded offline parser technology**.
This fresh review covers the earliest P16 JSON/canonicalization component only. The
previous v2 decisions are historical evidence, not completion of this review.

## Constraints and alternatives

The component accepts immutable UTF-8 software-statement bytes, <=65536 bytes and
depth 8, rejects duplicate keys and float lexemes, and canonicalizes a closed ASCII
safe-integer subset. It performs no I/O, autonomous decision, control or sensor fusion.
Linux/macOS/Windows are software deployment targets, not physical qualification.
It is unsuitable as evidence of an MLS guard, CNSA deployment, hard real-time execution,
five-nines service or tactical accreditation. P17/P18 consumers must enforce separate
qualified boundaries; offline signature authentication cannot confer such properties.

Fresh candidate review includes:

- [CPython JSON hooks](https://docs.python.org/3/library/json.html): paired-key,
  integer-token and float-token callbacks allow pre-conversion lexical rejection.
- [Rust Serde](https://serde.rs/attributes.html): typed native structures and field
  attributes are credible for a native verifier; lexical/canonical-byte and cryptographic
  acceptance parity still require explicit contract evidence.
- [Jackson streaming](https://github.com/FasterXML/jackson-core): Java/Kotlin can constrain
  token processing independently of binding into application objects. A managed streaming
  implementation is a credible alternative, not excluded by installed tooling.
- [msgspec](https://github.com/msgspec/msgspec): a compiled validation candidate. Its
  general typed-decoding performance claims do not establish duplicate-field and lexical
  parity for this protocol, or target-hardware timing.
- [Node crypto](https://nodejs.org/api/crypto.html): maintained signature primitives do
  not themselves preserve JSON integer lexemes or duplicate fields. The prior independent
  probe remains evidence for that distinction, not a whole-verifier benchmark.

KEEP the Python parser for this bounded offline component: its raw-token hooks directly
satisfy the lexical contract, exact immutable bytes preserve signed input identity, and
no custom native parser or cryptographic arithmetic is needed. This is a constraints-based
selection, not incumbent preference or a claim of superior throughput. No candidate has
established a material deployment benefit for this particular offline contract. A target
native-runtime requirement or measured bottleneck requires a new comparison; this decision
does not select the language of P18 hardware paths.

## Observed mismatch and executable correction

Previously `json.loads` converted integer tokens using its default arbitrary-precision
integer conversion before the schema rejected values outside the safe-integer range.
A byte/depth budget did not establish the tighter numeric-token conversion bound.
Interpreter-wide integer digit limits also vary with runtime/configuration and exceed
this protocol's numeric range; they are not the protocol gate.

A new regression places a sentinel at payload shape validation. Four out-of-range tokens
(3000 digits, 17 digits, safe maximum plus one, and negative one) reached that sentinel
before the fix. A `parse_int` callback now rejects them lexically before `int` conversion.
Valid zero, negative-zero canonicalization and maximum safe integer remain compatible.
No frozen wire threshold or signature algorithm changed. The inherited P1 byte/depth
checker was consumed without modification.

Validation: 33 passport/schema tests and 31 task/bundle/federation/inbox tests pass on
Linux Python 3.13.5. Initial four failures are retained in the lane checkpoint. No
native/hardware, full-repository or hosted qualification is inferred from these results.

Next earliest review: signature backend, trust metadata, expiry/revocation, then evidence,
schemas/tooling, tasks, bundle composition, federation, inbox, and P17/P18 scope/claims.
No V3 completion marker is justified at this point.
