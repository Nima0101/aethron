# Direct offline federation v1

Federation narrows which authenticated software statements a local trust domain can
accept. It never gives a self-declared capability execution or motion authority and
never establishes evidence truth, accreditation or ownership of a real-world domain.
Domains are local software-policy aliases, not persons, devices, URLs or network names.

## Technology decision

Requirements: offline immutable snapshots on Linux/macOS/Windows, at most 16 direct
peers, exact byte pins, explicit issuer/capability scope, no transitive trust, current
time and independently persisted revision floors. No network identity service, rule
extensions, dynamic hierarchy, scheduler or real-time control is required.

Compare [Cedar](https://docs.cedarpolicy.com/overview/terminology.html) scoped policies
and entity hierarchies, [OPA/Rego](https://www.openpolicyagent.org/docs/policy-language)
declarative policies, [SPIFFE trust domains](https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/),
and a closed table interpreted in Rust, Java/Kotlin, .NET or Python. The first two are
credible choices for a policy language, but this profile deliberately has no rule
language or hierarchy. SPIFFE is a workload identity framework, not evidence of an
artifact's capability. None substitutes for the signed passport and exact evidence.

Select closed canonical JSON with a Python bounded table evaluator. The decisive
properties are direct exact-match semantics, a fixed linear scan of at most 16 rows,
[lexical JSON rejection hooks](https://docs.python.org/3/library/json.html), immutable
byte snapshots and composition through the public bundle verifier. Rust/managed typed
tables could meet the same contract, but no native deployment, throughput or memory
requirement establishes a material migration benefit here. Existing component bounds
and negative contract tests evidence the choice; no installation/familiarity preference
or performance superiority is claimed. A rule-language requirement reopens selection.

## Snapshot contract

Exact UTF-8 bytes, at most 65536 bytes, depth 8. Closed objects, no duplicate fields,
float lexemes, nonfinite numbers, boolean numbers, non-ASCII identifiers or unknown
capabilities. Canonical encoding follows passport v1's ASCII/safe-integer subset.

Root fields are `version` (integer 1), `revision` (positive safe integer), `local_domain`
(passport identifier grammar), `issued_at`, `expires_at` (safe UTC seconds, positive
lifetime at most 3600), and `peers` (0–16 rows). An empty table denies every peer.
Each row contains exactly `remote_domain`, `policy_sha256`, `issuers`, `capabilities`.
Remote domains are unique and differ from the local domain. The policy pin hashes exact
passport trust-policy bytes. Issuers are 1–16 unique aliases. Capabilities are 1–3 unique
members of the passport v1 vocabulary. Wildcards and delegation fields are rejected.

`verify_federated_bundle` requires caller-authenticated `expected_federation_sha256`,
`local_domain`, `remote_domain`, `minimum_federation_revision`, and all public task-bundle
arguments. It checks the canonical snapshot pin, exact local/remote domain, time and
revision floors, and the selected peer's exact policy pin. It then invokes the public
bundle verifier, and restricts the authenticated passport issuer and every declared
capability to the selected row. A trusted peer cannot introduce another peer or enlarge
scope. Updated/revoked snapshots require a fresh authenticated pin and revision floor;
the library does not fetch snapshots or persist caller high-water marks.

The result carries immutable digest/revision/expiry/evidence metadata only. Expiry is
the minimum of federation, task, passport and policy expiry. All authority/qualification
flags remain false. Failure clears metadata and does not echo inputs. Input evidence
limits remain those of task-bundle v1; federation adds at most 64 KiB. No cached admission,
remote transport, transitive chain or actuation is implemented.
