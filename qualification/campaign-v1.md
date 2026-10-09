# P15 capture campaign contract v1

`qualification.campaign.evaluate(plan_bytes, captures)` checks a preregistered
case matrix against bounded capture declarations. No hardware is accessed and
no perception, actuator, field or certification authority is granted. Scope is
declaration coverage only, not accuracy, sample independence or held-out data.

The plan is strict UTF-8 JSON bytes, maximum 65,536 bytes/depth 8, with no
duplicate/unknown fields, nonfinite numbers or boolean integers. Root fields:
`version` (integer 1), `rig_sha256`, `domain_sha256`, `procedure_sha256`, `cases`.
Digests are lowercase SHA-256 hex; the rig digest uses the canonical v1 rig
serialization. Domain/procedure references must be frozen before capture but
this checker cannot prove preregistration, authenticity or their contents.

There are 1–16 cases. Each has exactly `id` (unique v1 token), `lighting` (v1
lighting enum), `required_sensors` (1–5 unique v1 sensor kinds), `evidence` (v1
evidence enum), `minimum_captures` (integer 1–64). The sum of requested captures
must be <=64. No live platform, physical range or performance threshold can be
declared through this schema. These are offline work bounds, not altered runtime
acceptance thresholds.

`captures` is an exact built-in list, length 0–64. Every entry is an exact dict
with `case_id` (v1 token), `manifest` (immutable bytes <=65,536), `now_ms` (v1
non-boolean integer). The instant is caller-supplied in that manifest's reference
clock domain. Total manifest input is bounded by 4 MiB. Callers must not mutate
the list/dicts during evaluation; memory allocated before calling is outside
this function's budget. Invalid plan/input structure raises fixed
`ValueError("invalid_capture_campaign")` without input text.

For each entry, run the unchanged v1 declaration validator. Retain malformed
and failed declarations as fixed findings in the report. Require the planned
rig digest; all required sensors; each required sensor's environment lighting;
and the planned evidence category on every record. Unknown case IDs fail
coverage. An exact manifest repeated anywhere in the batch invalidates *every*
occurrence, including across cases, so input ordering cannot select a winner.
Different JSON formatting can change the byte digest; this duplicate check is
not a scientific claim of independent acquisitions or sample uniqueness.

Reports contain `plan_sha256`, `captures_sha256`, aggregate capture counts, sorted fixed findings,
and per-case ordinal/required/eligible counts. They exclude case IDs, rig/domain
references, timestamps and sensor data. `declaration_coverage_complete` requires
every case's minimum and no rejected/unknown/duplicate captures. Extra *valid*
captures for a planned case do not increase that case's requirement. Every
failed submitted attempt remains visible; never delete negative inputs to make
the matrix appear complete. Physical qualification, domain/procedure evidence
verification and artifact authenticity are always false. Input hashes are
linkable and not anonymization. Artifact byte matching remains a separate API.

The capture commitment is SHA-256 of ASCII
`aethron.qualification.captures.v1` followed by a zero byte and compact ASCII JSON
of sorted `[case_id, manifest_sha256, now_ms]` triples. Sort lexicographically by
case ID, then lowercase digest, then integer instant; retain duplicate triples.
This binds exact manifest bytes and trusted evaluation instants while making
submission order irrelevant. It is not a signature or proof of acquisition.

## Capture procedure

1. Device/domain owner freezes the exact rig configuration, domain description,
   procedure and case matrix before collecting any qualifying inputs. Real
   device access, rights, safety/privacy approval and instruments are external
   gates, not booleans this tool can approve.
2. For authorized tests, retain calibration validity, clock-domain/skew evidence
   and environmental declarations for each required sensor. Use the P2 producer's
   versioned capture contracts; this module does not implement a competing
   sensor adapter or save live tracks/imagery.
3. Supply each minimized capture declaration and its independently chosen
   evaluation instant. Preserve loss, invalid calibration, clock faults and
   other failed attempts. Do not relabel synthetic/recorded evidence as physical.
4. Review the coverage report alongside artifact byte matching, evidence
   authenticity, data-rights/held-out evaluation and independent domain review.
   Matching bytes/complete declarations do not close those external gates.

## Technology decision — 2026-10-10

Constraints are bounded offline metadata, cross-capture joins, deterministic
diagnostics, no device SDK and no hard real-time requirement. [CUE closed
constraints](https://cuelang.org/docs/concept/how-cue-enables-data-validation/)
can validate declarative structures; [JSON Schema
conditionals](https://json-schema.org/understanding-json-schema/reference/conditionals)
cover local shape dependencies. Both still need a host adapter for opaque
manifest bytes and the established declaration evaluator. [Python JSON
hooks](https://docs.python.org/3.13/library/json.html) plus explicit bounded loops
permit those joins and fixed errors in one auditable offline module. Select that
approach for this contract; no language preference or measured speed superiority
is assumed. Plan: failing synthetic coverage/duplicate/binding tests first, then
implementation, targeted tests, lint/security and source-bound evidence.
