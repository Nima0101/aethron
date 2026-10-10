# P4/P15 software and acceptance inventory — 2026-10-10

Reviewed baseline: `1c0c111b59300b6563d591c82624f24ac217a7a6`, plus the bounded
software assessment accompanying this inventory. **P15 is incomplete.** Physical
qualification remains external, but that does not make the unfinished software
below externally blocked or complete. No device/domain/customer acceptance is
granted by a declaration, matching digest, local test result or workflow file.

The review restarted at the earliest declaration contract and followed artifact
binding, campaign coverage, reference binding and bundle consumption. The current
interfaces retain their explicit bounded byte/time semantics and non-qualification
flags. The [component technology review](technology/review-v3.md) remains applicable
to those offline source-checkout constraints; no new target ABI, SDK, throughput or
hard-deadline requirement was established by this review. This inventory does not
claim a completed technology audit of every future deliverable.

| Area | Implemented evidence | Remaining software or integration work |
|---|---|---|
| Rig/calibration/clock/lighting declarations | [v1 schema](schema-v1.md), [validator](evidence.py), [negative cases](tests/test_evidence.py) | No temperature, weather, vibration, EMC, power or device-measurement schema. Any extension needs a versioned contract and tests; actual observations remain external. |
| Artifact binding | [Bounded immutable-byte checks](artifacts.py), [negative tests](tests/test_artifacts.py) | Content truth, instrument authenticity and source authorization are not implemented here. Consume the producing trust/source contracts through an owned adapter when published. |
| Campaign matrix and attempt retention | [Coverage evaluator](campaign.py), [tests](tests/test_campaign.py) | Caller-supplied cases cover sensor/lighting/evidence declarations only. No independently authenticated acquisition ledger or proof of complete submission. A local recording/ledger requirement still needs a privacy-scoped design; it cannot be inferred from this report. |
| Domain/procedure references | [Opaque hash checks](campaign_references.py); [checklist declarations](procedures-v1.md); [domain matching](domains-v1.md); [method references](methods-v1.md) | Method-byte binding and declarations of current software rules now supplement checklist/domain checks. Physical acquisition-method specifications, additional environment dimensions and human-review evidence validation remain unfinished; supplier/field approval remains external. |
| Bundle and process transport | [Composition](campaign_bundle.py), [bounded stdin](campaign_bundle_cli.py), [integration tests](tests/test_bundle_artifact_integration.py) | Source-checkout tooling only; the qualification harness is not shipped in the installed wheel. An installed distribution/consumer acceptance path is still needed. No producer-device capture adapter is implemented by this lane. |
| Portable consumer evidence | [Six synthetic vectors](consumer-vectors-v1.md), [runner](tests/test_consumer_vectors.py) | Reference Python execution only. Published peer/native consumers must demonstrate their own conformance; fixture portability alone is not successful interoperability. |
| Technology diagnostics | [Review controls and limitations](technology/review-v3.md), [hosted retention](technology/workflow-retention-review-v3.md) | Local synthetic diagnostics are not target latency, uptime, coding-standard certification or release attestation. Historical failures and finite-corpus limits remain applicable. |
| P19 reusable acceptance, including help | No installed-release or help-coverage validator implemented under `qualification/` | Locally implementable validation remains: exact-release inventory coverage, role/locale correspondence, contextual links, negative cases and evidence association. Producer inventories, UI/help integration and installation belong to their owning lanes. Final acceptance also requires the actual installed product and independent user evidence. |

## Non-actuating integration boundaries

P2 and P16/P18 produce authorized source/transport and clock contracts. P15 consumes
published versions; it does not implement competing sensor or trust services.
Required evidence includes corruption/version/encoding rejection, source permission
failures, clock provenance, unavailable states and retained negative observations.
Current minimized manifests alone do not supply this evidence. A missing peer
contract is an integration dependency; synthetic fixture and adapter software can
still proceed independently without a physical-pass claim.

P11 supplies installed release/startup/recovery/resource observations. P12/P17
supplies actual operator states, permissions and help integration. The P19 lead
owns the integrated acceptance matrix and final customer-installation evidence.
P15's reusable checkers must bind these inputs to the exact release, deployment
profile, role and language; matching a file hash does not establish truthful
content or a successful independent acceptance session.

Physical instruments, authorized real-device access, representative field data
and independent certification remain external gates. Missing software validators,
packaging, fixtures or adapters remain unfinished software. No hardware claim is
made for these synthetic vectors. Insufficient information for tactical deployment.

## Current corrective slice and next checkpoint

The consumer examples previously required Python fixture builders to construct
several important input combinations. The new tracked JSON corpus and reference
tests make six existing non-qualifying outcomes directly reusable while retaining
all failure groups. This is evidence portability, not a new sensor capability.

The non-executing [checklist contract](procedures-v1.md) now provides bounded
declaration and coverage checks with explicit unknown/unverified states and
negative fixtures. The [domain declaration contract](domains-v1.md) now checks
whole lighting/sensor/evidence tuples against campaign cases in both directions.
The separate [method-reference contract](methods-v1.md) binds supplied method
bytes and validates declarations of existing software rules. It authenticates no
human review and does not describe or execute physical acquisition procedures.
The [software assessment](assessment-v1.md) composes these gates with campaign
coverage and supplied capture artifacts, retaining independent negatives and
bounding all artifact payloads together. It accepts no precomputed approvals.
The next independent software checkpoint is portable assessment vectors and a
bounded process-consumer path for the same versioned raw-input contract.
Target-device procedures and physical acceptance cannot be inferred from
declaration completeness. No completion marker is justified by this inventory.
