# Passive comparator coverage review v3

Routing review baseline: `e296382529b9f59e25f56c077e679bbba610e16b`.
This is a finite synthetic evidence review, not complete receiver equivalence or
a production KEEP/MIGRATE decision. No runtime adapter or driver changed.

The original wire corpus edits sender/component header bytes without updating
CRC. Those cases establish rejection of those bytes but do not independently
establish routing-filter enforcement. Two additive fixtures, named
`v3_sender_valid_crc` and `v3_component_valid_crc`, use the pinned SDK encoder
with a different system or component ID. The same packet is accepted with its
matching route and rejected as `sender_mismatch` by the ordinary `(1, 1)` route.
Acceptance remains unverified and perception-ineligible. CRC validity does not
authenticate the sender.

The original 17 fixtures remain identical, including their names and bytes.
At that revision the wire harness runs 19 cases. The native harness inherits both additions
through its existing wire-corpus composition: 35 cases/67 steps, with no new Rust
execution claimed here. The separate managed lifecycle corpus remains 16 cases/
48 steps. Historical receipts retain their original corpus and source hashes;
their passes do not cover these new fixtures.

| Contract property | Evidence scope after this correction |
| --- | --- |
| Two message layouts, zero trimming and finite values | Existing wire cases; finite examples only |
| Bad CRC and framing rejection | Existing wire cases; not an exhaustive malformed-input proof |
| System/component routing filters | New CRC-valid negative fixtures plus matching-route positive controls |
| Expiry, close, clock rollback, sequence/boot transitions | Existing lifecycle corpus; managed execution and historical native execution have separate receipts |
| Raised supplied-clock exceptions and cancellation | Dedicated Python receiver tests; absent from the cross-language corpus |
| Caller-owned snapshots and exact object disposal | Dedicated diagnostic inspection; absent from the cross-language corpus |
| Full constructor validation, signed replay, UDP and installed dependency equivalence | Not established by the comparator corpora |

The [source-bound receipt](robotics-routing-coverage-v3.json) records two RED
assertions for the absent fixtures, 41 passing focused harness methods, and the
normal/sanitized C run. A temporary audit-driver copy removes only the routing
checks. Under the existing typed/numeric comparator, that copy passes all original
17 cases but fails both additions. The repository driver is unchanged. This
negative control demonstrates test discrimination; it does not report a defect
in the production receiver or authorize a transmit path.

The initial negative-control inspection used exact dictionary equality and failed
on C's decimal rendering of accepted binary32 values. The existing comparator
accepts those original values and rejects the two new admission mismatches. That
failed inspection is retained; no numeric tolerance or acceptance threshold was
changed. Incidental harness timings remain in the raw receipt without a runtime
ranking or deployment claim.

This fixture correction uses the existing SDK encoder and test harness. It does
not select a new technology or extend a candidate implementation. Missing target
constraints and unequal candidate work remain unresolved. The earliest passive
component decision stays PENDING; later component reviews remain incomplete.

## Compatibility-flag coverage supplement

Reviewed baseline: `dfc7edbd3625bca651a046380b7781113754fc98`.
The original compatibility-flag mutation also has an invalid CRC. Preserve that
case and append `v3_compatibility_flag_valid_crc`, rebuilding its checksum with
the pinned SDK CRC implementation and the ATTITUDE message's CRC extra byte.
A direct SDK decode accepts the packet, while the adapter rejects it as
`unsupported_packet`, with no samples and no perception eligibility. This tests
the existing diagnostic profile's zero-flag restriction. It is not a MAVLink
requirement: the [official serialization specification](https://mavlink.io/en/guide/serialization.html#compatibility-flags-mavlink-2)
allows implementations to ignore unknown compatibility flags. That narrower
profile must not be described as complete protocol compatibility.

All previous 19 fixture records are unchanged. The wire corpus now contains
20 cases; generated native fixtures contain 36 cases/68 steps. No new Rust
execution is claimed; the separate managed corpus remains 16 cases/48 steps.
The [flag coverage receipt](robotics-flag-coverage-v3.json) retains the absent-case
RED assertion, 42 passing focused methods, and normal/ASan/UBSan C parity. It also
retains an initial test-command import error caused by naming a nonexistent
managed test module, followed by the corrected invocation.

A temporary C audit-driver copy removes only the `p[3]` guard. The unchanged
comparator accepts its first 19 results but rejects its acceptance of the new
case. The repository driver and production receiver remain unchanged. This
isolates a local admission-policy check; it does not establish exhaustive header
coverage, signing safety, authenticated provenance or full runtime equivalence.
Incidental timings remain in the receipt without a performance ranking.

This is a correction to existing offline experiment fixtures, using the installed
SDK to encode/check its own wire contract. It introduces no runtime technology.
The production technology decision remains PENDING and later components remain
unreviewed. Remaining old header mutations should not be interpreted as isolated
checks: the unknown incompatibility flag and unsupported message also alter CRC;
the signed-flag mutation also lacks its signature trailer; and the v1 marker
mutation is not a valid v1 frame.
