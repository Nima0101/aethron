# P16 direct federation review v3

Baseline: `73cf95b0b6df7e827531eb70bb74660f13314dd7`. Reviewed 2026-10-10.
Decision: **KEEP bounded direct table; FIX coverage; CLARIFY caller trust and lifetime claims**.
Production implementation and portable vectors are unchanged.

## Constraints and candidate review

The current component checks local immutable software descriptions against an externally
pinned table of at most 16 peers. Requirements are strict bounded JSON, canonical byte
identity, explicit issuer/capability membership, whole-table shape validation, no trust
transitivity, independent caller-supplied time and revision floors, and no authority grant.
It does not implement workload enrollment, radio transport, distributed consensus,
operator authorization or a physical control path. No target CPU, memory budget,
throughput SLA or physical timing evidence establishes a runtime performance requirement.

| Candidate | Source-bound comparison |
|---|---|
| Python bounded table | [JSON hooks](https://docs.python.org/3.13/library/json.html) preserve duplicate fields and integer tokens for explicit rejection. A fixed closed table and public bundle-verifier composition implement the required checks without evaluating user-defined rules. All rows are checked, not only the selected one. |
| Rust/Serde typed table | [Visitor interfaces](https://docs.rs/serde/latest/serde/de/trait.Visitor.html) support explicit map and numeric validation. A credible native implementation can preserve the same bounded semantics; lexical and canonical requirements still require deliberate validation. Native speed is not measured in this review. |
| Cedar | [Cedar concepts](https://docs.cedarpolicy.com/overview/terminology.html) separate authentication from policy authorization and support principal/action/resource conditions and entity hierarchies. Cedar is credible for a richer application policy, but those expressive rules are outside this fixed, non-authorizing metadata profile. Its use would not authenticate the external table pin. |
| OPA/Rego | [Rego](https://www.openpolicyagent.org/docs/policy-language) evaluates declarative rules over structured data. It can express membership rules, but raw byte canonicality and lexical rejection still need an input boundary. The current contract has no extensible rule-language requirement. |

KEEP the closed table and current interpreter: bounded lexical validation and simple
membership checks match this contract without adding a separate rule evaluation surface.
Cedar and Rego are serious domain alternatives, not substitute names for languages already
in the component. Rust remains credible for a concrete native consumer. None establishes
a material migration win under the current requirements/evidence; this does not rank
speed or prove Python universally best. Installation, familiarity and rewrite cost are
not reasons. Any migration must retain v1 bytes, whole-table rejection and false authority.

## Findings and evidence

Eight baseline federation tests passed. Three new tests demonstrate:

- a malformed unselected peer rejects before bundle verification, after a valid two-row
  control passes;
- issuer-scope rejection after calling the real bundle verifier returns no digest,
  revision, expiry or evidence and leaves every authority/qualification flag false;
- a later federation expiry cannot extend the task/bundle expiry, including at its
  exclusive boundary.

The saved positive result in the scope test remains unchanged after a later rejection.
This is retained negative evidence: the function does not revoke previously returned
objects or establish replay protection. It accepts caller-supplied time/floors and cannot
verify that the caller persisted them. Domain aliases are not endpoint authentication
or privacy guarantees. Documentation now states these limits instead of saying failure
“clears” metadata in a way that could imply stateful revocation.

No production defect was demonstrated; added cases pass the unchanged implementation.
No production RED/fix, hardware timing, MLS, CNSA, cross-domain accreditation or uptime
qualification is claimed. The broader P17/P18 scope remains unqualified and incomplete.

Reproduce using the pinned conformance environment:

```sh
python -m unittest discover -s tests -p test_interop_federation.py -v
python -m unittest discover -s tests -p 'test_interop*.py'
python -m unittest discover -s tests -p 'test_passport*.py'
```

[Source bindings and results](p16-federation-v3-results.json) retain local verification.
Next earliest component: P16 bounded inbox. V3 and lane completion remain pending.
