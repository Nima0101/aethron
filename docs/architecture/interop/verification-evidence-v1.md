# P16 verification evidence boundary

P16 implements local software-statement verification, bounded in-memory buffering and
explicit local policy and federation floor stores.
Passing an example, a unit test or a configured CI job does not establish an installed
customer product. This page describes how to interpret the existing checks; it adds no
release gate implementation, transport, persistence or qualification claim.

## What the implemented APIs establish

| API | Successful result establishes | Still required from the caller |
|---|---|---|
| `verify` | Signature and statement match the supplied policy, subject digest and time/floors. | Authenticated policy provisioning, expected artifact identity, trusted time and durable floors. |
| `validate_pinned_policy` | Complete policy metadata and exact bytes match an externally trusted pin and supplied time/floors. | Pin authenticity, key enrollment and independent persistence, including policies that revoke every signer. |
| `verify_evidence` | Supplied bytes match every signed evidence reference. | Content validity, rights and permitted handling; failed/unknown outcomes remain assertions. |
| `validate_task` | Canonical verification description matches the expected task and subject pins and current supplied time. | Pin authenticity, referenced input verification, replay handling and authorization. |
| `verify_task_bundle` | Exact local inputs satisfy the task pins/budget and current supplied passport policy. | Freshness at use and independent authority; saved results do not expire themselves. |
| `validate_pinned_federation` | Complete canonical table matches the external pin, local domain and supplied time/revision floors, including an empty deny-all table. | Pin/time authenticity, durable floors and fresh peer/bundle verification; referenced policies are not authenticated. |
| `verify_federated_bundle` | The direct pinned federation table permits the statement under its selected peer row. | Provisioned domain aliases and pins; network identity, trust enrollment and floor persistence. |
| `BoundedInbox` | Local quota/expiry accounting and opaque byte retention. | Authenticated peer aliases, trustworthy monotonic time and verification after dequeue. Closing does not revoke returned copies. |
| `FederationFloorStore` | Committed federation revision/digest and trusted-time floors, including deny-all snapshots. | Clock/pin authenticity, protected local storage, whole-store rollback detection and fresh verification at use. |
| `PolicyFloorStore` | Committed policy revision/digest and trusted-time floors on cooperating local storage. | Clock/pin authenticity, protected storage, independent detection of whole-store rollback, and fresh verification at use. |

These are application values and checks, not unforgeable authorization tokens. The
stateless verifiers do not persist floors; the separate [policy](policy-floor-store-v1.md) and [federation](federation-floor-store-v1.md) stores
require explicit initialization and caller use. P16 does not fetch policy updates or provide durable synchronization,
cancel work already taken by a consumer or sample a completion-time clock. Logical
byte ceilings do not establish process-memory or worst-case execution-time bounds.

## Source, installation and hosted evidence are different

The [workflow](../../../.github/workflows/aethron-passports.yml) configures these jobs:

| Job | Configured scope | Evidence limit |
|---|---|---|
| `passports` | Python 3.9/3.13 on Linux/macOS/Windows, optional crypto import, source tests, installed-module identity and isolated installed vectors. | Optional schema tests can skip in this job. Matrix configuration is not proof that every combination ran or passed. |
| `schema-conformance` | Python 3.13, explicit schema/crypto imports, structural and actual-verifier comparisons. | Structural conformance does not establish authentic signatures, complete references or lexical equivalence by itself. |
| `sensor-conformance` | Python 3.13 packaging checks, selected source-archive input comparison, installation from that archive, isolated installed P16 checks, then producer-consumer tests. | The last consumer tests set `PYTHONPATH=.:integrations/edge` and exercise source imports. They do not prove installed P2/P3 consumer integration. |

The packaging diagnostic artifact contains eight selected context/check outputs, not
the source archive or resulting wheel. It is configured for fourteen-day retention and
upload after failures; existence is never a PASS result. Missing or partial diagnostics
remain missing evidence. GitHub documents [artifact retrieval and expiration](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts).

Before citing a hosted result, retain the run URL/ID, attempt, job conclusions and actual
checkout revision. Compare them with the intended release revision and preserve failed
or skipped checks. The workflow records `git rev-parse HEAD` separately from event
context; a PR checkout can be a merge revision rather than the branch head. GitHub's
[context reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)
defines the run metadata. Neither a workflow file, artifact name nor digest alone
authenticates a release or proves its checks succeeded.

The [passport examples](../../../examples/passports/README.md) use public synthetic
keys and artificial times. Running their two Python snippets from a checkout validates
those snippets against that source environment. It does not repeat the documented
installation command, test a clean customer installation or establish hosted execution.

## Current scope and unresolved work

The [current inventory](../../engineering/reviews/p16-p18-inventory-v3.md) records
component decisions, corrections and missing software. Earlier result records describe
their own revisions and experiments; they do not automatically certify later HEADs.
Source hashes establish listed-file byte identity only, not loaded-code identity,
complete dependencies, signed release provenance or truth of the reported observations.

Provisioning, independent whole-store rollback detection,
remote transport and integrated runtime conformance remain unfinished P16 software.
The local floor helpers do not close those gaps. P17 command-platform, P18 physical/real-time and P19
installed-product/help acceptance are not established by these library checks. A
similarly numbered phase-1 evidence file is not evidence for those later phase scopes.

No MLS or cross-domain guard, CNSA accreditation, encrypted transport, Link 16/DDS
interoperability, five-nines availability or physical real-time qualification is claimed.
Insufficient information for tactical deployment.
