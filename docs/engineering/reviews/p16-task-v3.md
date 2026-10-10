# P16 task description review v3

Baseline: `0686debb698f84299b0fa4531448ca1b803e88a7`. Reviewed 2026-10-10.
Decision: **KEEP bounded Python validator; FIX coverage; CLARIFY trust and lifetime claims**.
Production code, canonical encoding, fixture bytes and accepted task kinds are unchanged.

## Constraints and technology reassessment

This is a stateless offline description checker, not a task executor or scheduler.
Its contract is immutable UTF-8 bytes up to 64 KiB, depth eight, exact safe integers,
closed fields, two verification-only kinds, a 300-second lifetime, externally
provisioned digest pins and caller-trusted time. It neither acquires nor interprets
physical sensor data. There is no deployed throughput, RAM or hard-deadline target
against which a runtime performance winner can be asserted. Whole-document admission,
lexical rejection and canonical byte equality are decisive here.

| Candidate | Source-bound properties and fit |
|---|---|
| Python standard JSON with bounded hooks | [Python 3.13 documentation](https://docs.python.org/3.13/library/json.html) exposes object-pair and integer-token hooks. The shared parser rejects duplicates and bounds integer tokens before conversion; exact byte equality rejects alternative spellings. This provides the required distinctions without implementing a JSON tokenizer. Default decoding alone is insufficient. |
| Rust with Serde | [Visitor API](https://docs.rs/serde/latest/serde/de/trait.Visitor.html) supports explicit typed/map traversal. A native implementation can enforce duplicates, fields and bounds with controlled ownership. Raw number spelling and canonical-byte rules still require deliberate handling. No benchmark here ranks its speed or memory against Python. |
| C# with System.Text.Json | [Utf8JsonReader](https://learn.microsoft.com/en-us/dotnet/api/system.text.json.utf8jsonreader?view=net-10.0) is a forward-only UTF-8 token reader exposing value spans and token kinds. It is credible for bounded lexical validation without building a general object tree. It still needs duplicate tracking, canonical ordering and task-specific checks. |
| Elixir with Jason | [Jason options](https://jason.hexdocs.pm/Jason.html) include ordered objects, binary strings and string-copy control. These support immutable data processing, but its documented decode options do not provide an integer-token callback equivalent to this profile's lexical bound. A lexical adapter would need separate evidence; dynamic atom decoding must not be used on untrusted keys. |

KEEP the current implementation for these constraints: documented token/pair hooks plus
explicit bounded checks implement the necessary semantics with no custom tokenizer.
The native readers remain credible alternatives for an actual memory/deadline deployment;
none establishes a material win for this offline contract on the evidence available.
This is a requirements-based decision, not a comparative performance result. Tool
installation, incumbent preference and rewrite effort are not selection criteria.
Preserve the v1 bytes for any later migration and require the same negative cases.

## Claim corrections and executable evidence

The old prose incorrectly called the already-present bundle verifier a future consumer
and suggested evidence revocation without specifying the actual key/statement policy
lists. It also omitted that a saved successful result is just a snapshot: it does not
expire itself, prevent replay, authenticate a caller or grant execution authority.
Task IDs and digests are not privacy guarantees. The updated contract names these limits.

Seven original task tests passed before changes. Three added tests check every public
rejection reason for absent digest/expiry metadata and false authority, demonstrate
that canonicalization cannot establish freshness or authenticate an extended lifetime,
and retain the negative fact that repeated validation succeeds before expiry. A later
expired call rejects even when a previous result remains in memory. These tests pass
against the unchanged production implementation: this review found documentation and
coverage gaps, not a demonstrated production defect, so no production RED/fix is claimed.

No separate task JSON Schema is present in this baseline. The normative contract is the
closed validator and versioned task document, with seven portable task vectors. The
three published JSON Schemas cover passport documents only. This review does not claim
that they validate task requests or that task-schema publication is complete.

Reproduce in the pinned conformance environment:

```sh
python -m unittest discover -s tests -p test_interop_tasks.py -v
python -m unittest discover -s tests -p 'test_interop*.py'
python -m unittest discover -s tests -p 'test_passport*.py'
```

See [source bindings and results](p16-task-v3-results.json). No physical, cryptographic
accreditation, MLS, availability or real-time qualification follows from these tests.
Next earliest component: P16 bundle verification. V3 and the lane remain incomplete.
