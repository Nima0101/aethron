# P16 ADR publication checks, review v3

Baseline: `97eaef42df8298e38359bf91287118ef7a659efd`, reviewed 2026-10-10.
Decision: KEEP JSON Schema 2020-12 and the offline validator; FIX continuous
validation coverage. Runtime code and wire contracts are unchanged.

The earliest parser/policy source was reread, including the independently pinned
policy entry point. Its exact-byte, bounded lexical and caller-trust limits remain
explicit. The bridge commit matches its parent, eight requested paths, recorded
bytes and noreply identity. This review addresses the next documentation-tooling
gap; it does not claim completion of the whole retrospective phase review.

## Finding and correction

The previous slice checked the new ADR and eight malformed records manually. Neither
the published ADR nor its schema was included in the continuing schema tests. The
workflow also omitted the ADR path, so a change to the decision alone would not
trigger that workflow. The earlier result remains a valid historical local check;
it did not establish continuous coverage.

The schema suite now includes the ADR schema in its closed-object and local-reference
inspection, validates every `docs/decisions/p16-*.json` record, and fails if that
inventory is empty. Three new methods exercise the published record, missing/extra
fields, field bounds and HTTPS-reference shape without an optional format checker.
The pull-request and main-push path filters now include those decision records.
The existing schema job executes this suite and explicitly imports its dependencies.
No hosted run or branch-protection requirement is inferred from workflow source.

The new tests pass the existing schema: this is a coverage correction, not a new
production defect or a fabricated RED/fix. A local schema copy with the reference
pattern removed accepts `not a URI`; the real schema rejects it. That control
demonstrates sensitivity to the earlier missing-format-enforcement problem without
rewriting a project file. The checker rejects 25 malformed document variants.

## Requirements and technology reassessment

This component validates trusted repository documentation during development/CI. It
needs JSON Schema 2020-12, rejection of extra/missing fields, deterministic negative
fixtures, local-only schema resolution, and a check independent of optional format
packages. It has no real-time, target-device, runtime-service or throughput requirement.
Source records are not authenticated operational inputs, and schema success cannot
establish the truth of their claims.

| Candidate | Decisive evidence and boundary |
|---|---|
| Python jsonschema | Supports an explicit draft validator, schema checks and a supplied registry. Its documentation distinguishes optional format assertion from schema annotations. This suite explicitly denies remote retrieval and tests reference shape without a format checker. [Primary documentation](https://python-jsonschema.readthedocs.io/en/stable/validate/). |
| JavaScript/TypeScript Ajv | Supports 2020-12 through its corresponding validator class; dialect configuration and format behavior require explicit selection. A credible independent validator, not excluded by repository language. [Ajv documentation](https://ajv.js.org/json-schema.html). |
| Java networknt | Documents 2020-12 support and configuration for format assertions. A credible managed implementation; its presence would not itself make this ADR corpus part of CI. [Official repository](https://github.com/networknt/json-schema-validator). |
| C++ Sourcemeta Blaze | Documents 2020-12 support and a native validator. Its advertised performance is not a measurement of this corpus and does not establish a benefit for these small offline documentation checks. [Official repository](https://github.com/sourcemeta/blaze). |

KEEP the current validator because explicit dialect/registry controls and executable
negative cases satisfy the structural contract; preserve the portable schema as the
interchange boundary. None of the reviewed alternatives demonstrates a material win
against this component's actual requirements. The finding is missing test discovery
and workflow triggering, which is corrected directly. No comparative speed ranking,
installation convenience or rewrite-cost argument justifies this decision. Runtime
selection for any future component remains separate.

## Verification and limits

Three new methods pass; 26 related schema/policy methods pass with zero skips.
Ruff, formatting, Bandit, actionlint and diff checks pass. Commands, source bindings
and retained logs are recorded in [the result](p16-adr-publication-v3-results.json).
These tests validate document structure and reference shape only. They do not prove
reference reachability, author identity, evidence authenticity, decision quality,
installed-distribution behavior, physical qualification or full phase completion.

Next earliest unreviewed boundary: installed-package behavioral coverage of the new
policy API. Persistent floors remain unfinished software. No audit-complete marker
or weapon-related implementation is introduced.
