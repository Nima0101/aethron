# Authenticated snapshot-to-plan binding: fresh V3 review

Decision: **KEEP bounded synchronous streaming; FIX documentation and cleanup
failure coverage.** Reviewed through `3a38b82bedd82bf4c92707d4fec011e27890b192`.
Production behavior, input format and bounds are unchanged. This review covers
`_copy_snapshot` and `create_rollout_plan`; signed wave claims in the same module
remain the next component, with their own timing boundary still to review.

## Constraints and technology comparison

Four fixed local files must be copied from a mutable directory, authenticated,
and bound to exact journal pins. At most five entries are inspected. Limits are
8192-byte manifest, 64-byte signature, 2048-byte policy and 8 MiB artifact; reads
use at most 64 KiB plus a final one-byte EOF probe. No file is executed. Trusted
caller dependencies are the clock, key, process and protected persistence/temp
storage. No target ABI, resident-memory budget, throughput SLA or hard deadline
is specified. Total process memory, filesystem latency and crash residue are not
bounded by the read buffer size.

Official sources were checked on 2026-10-10. These are engineering comparisons,
not unmeasured language speed rankings.

| Candidate | Requirement-relevant evidence and assessment |
| --- | --- |
| Python streaming/native hash and private directory | [Incremental hashlib](https://docs.python.org/3.13/library/hashlib.html) hashes successive chunks. [TemporaryDirectory](https://docs.python.org/3.13/library/tempfile.html) provides scoped cleanup with surfaced errors by default. Explicit byte accounting, hashing copied chunks and cleanup-before-persistence directly express the local contract. |
| Rust native adapter | [I/O copy](https://doc.rust-lang.org/std/io/fn.copy.html) supplies stream copying and may use platform acceleration. A bounded adapter can implement length/hash parity and explicit cleanup-result checks. Ownership is useful for descriptors; destructor-based cleanup alone must not imply that cleanup errors block persistence. No separate service or IPC is inherently needed. |
| C#/.NET stream adapter | [Stream.Read](https://learn.microsoft.com/en-us/dotnet/api/system.io.stream.read?view=net-9.0) supports bounded reads, including short reads. Explicit remaining-byte and digest logic can preserve the contract; managed disposal does not replace post-commit time validation. A CLR hosting requirement would favor this candidate, but none is supplied. |
| Erlang/Elixir file I/O | [OTP file reads](https://www.erlang.org/doc/apps/kernel/file.html#read/2) support bounded binary input. Supervision is credible for a concurrent transfer service; it does not establish snapshot authenticity, cleanup success or cross-store atomicity. No distributed transfer requirement exists here. |
| Kernel-assisted copy or mapping | Accelerated copies still require a private destination, explicit size/error handling and authenticated hashes. Mapping the mutable source cannot remove source mutation hazards. No measured transfer bottleneck establishes a benefit for this bounded path. |

KEEP rests on the explicit synchronous ordering over native I/O/hash operations,
recoverable read errors and a small auditable control surface. Other runtimes
can meet those properties; their type-system or hosting advantages do not yet
establish a material win for this component. Installed tools, familiarity and
rewrite expense are excluded. No candidate performance benchmark was run.

## Findings and executable evidence

The numbered main contract omitted the fourth clock check despite production
already checking after journal initialization. The old language rationale also
incorrectly required IPC for native candidates. Both are corrected. Cleanup
wording now distinguishes attempted context cleanup from guaranteed deletion or
secure erasure; process death and filesystem errors can leave residue.

The new test delegates to real temporary directories and real signed verification,
then injects an `OSError` at the plan context's exit after actual removal. It checks
that only the plan context is affected, the fixed public error suppresses injected
diagnostics, no journal is created and floors remain `(1, 900)`. This verifies
ordering when exit raises, not cleanup success under a real filesystem fault.

All 16 plan tests pass. Existing tests cover source replacement, truncation/growth,
exact hash/copy bounds, malformed or backward clocks, late expiry, preservation of
both committed stores and existing-journal evidence. The added test passes existing
production code; no artificial red-to-green claim is made. Historical
[V2 negative evidence](../verification/fleet-plan-technology-audit-v2.json) remains
unchanged. [V3 evidence](../verification/fleet-plan-review-v3.json) binds current
source/test bytes. Reproduce with:

```sh
PYTHONPATH=integrations/edge:build/fleet-linux-deps:tests/integration python3 -W error::ResourceWarning -m unittest test_fleet_plan -v
```

## Limits and next review

The snapshot is not an atomic capture of the source directory or a retained
payload cache. The floor and journal commits are not one transaction. Final time
is checked, not persisted; it cannot grant lasting operation authority. The
component has no installation, activation, network or actuation behavior. No
CNSA/MLS, real-time, uptime, physical durability or tactical deployment assurance
is established. Insufficient information for tactical deployment. Next earliest
review: signed wave-claim revalidation. No full-lane completion is claimed.
