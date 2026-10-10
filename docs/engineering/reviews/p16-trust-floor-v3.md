# P16 trust-floor lifecycle review v3

Reviewed 2026-10-10 at `7cb3c7e50142bab0206dcf30c5073b4da5d5611c`.
The preceding six-file ROS diagnostic commit was verified against its parent, recorded
bytes and noreply identity, then published to PR #35. This review re-read the earliest
passport parser/verification and evidence code, followed by tasks, bundles, federation
and inbox. It does not certify the entire phase or the unimplemented persistence layer.

## Finding and executable evidence

The verifier's caller contract required preserving accepted time/revision floors, but
neither the API documentation nor its tests explained a trap in deriving those floors
only from successful passport results. Rejections intentionally return no digest,
revision or expiry metadata. This correctly avoids treating rejected input as trusted;
it also means a caller cannot use rejection metadata to maintain configuration state.

Two new tests exercise actual signatures and actual policy/clock gates:

| Trace | Result |
|---|---|
| Revision 3 authenticates; independently trusted revision 4 revokes the passport | `revoked`, no result metadata |
| Caller supplies revision 3 and resets its floor to 3 | authentication succeeds again |
| Caller instead retains floor 4 | `policy_rollback`, no result metadata |
| Passport authenticates at 1500; trusted time advances to its expiry at 2000 | `passport_not_current`, no result metadata |
| Caller rewinds to 1500 and retains only its last successful time 1500 | authentication succeeds again |
| Caller instead retains trusted time floor 2000 | `time_rollback`, no result metadata |

All outcomes deny motion and evidence qualification authority. These are explicit
counterexamples to a consumer that persists only successful results, not newly
introduced production failures. The tests pass on the original verifier. They model
caller-supplied snapshots and floors; they do not execute a reboot, disk restoration,
clock service or persistence implementation. No RED failure is fabricated.

The public API docstring now explicitly separates independently authenticated policy
updates and trusted clock observations from per-passport success. The existing wire
profile, rejection metadata, frozen limits and executable verification logic remain
unchanged. Do not advance a floor using a revision or time merely supplied by an
untrusted envelope. Policy provisioning and trusted time remain external responsibilities.

## Requirements and technology reassessment

For the existing component, the constraints remain immutable bounded inputs, strict
lexical admission, native-backed signature verification and stateless offline calls;
there is no target timing SLA. KEEP the Python/native boundary and fix its consumer
contract evidence. [Python JSON hooks](https://docs.python.org/3/library/json.html)
permit raw number/key checks; [Jackson streaming](https://github.com/FasterXML/jackson-core)
in Java/Kotlin is a credible non-incumbent token-oriented alternative; Rust
[Serde attributes](https://serde.rs/attributes.html) support typed data admission.
All still require an explicit trusted-state lifecycle. Changing the parser's language
does not supply it. Current constraints and the direct executable traces establish no
materially winning parser migration; this is not a throughput comparison or a choice
of future persistence/runtime technology.

A storage subsystem is separate, unfinished software. [SQLite atomic commit](https://sqlite.org/atomiccommit.html)
offers transactional updates subject to documented filesystem/flush assumptions;
[LMDB's official mirror](https://github.com/LMDB/lmdb) identifies another native embedded
storage candidate. The LMDB documentation URL failed to load, so no comparative LMDB
behavior or performance claim is made. Neither project was installed or benchmarked.
Our inference: storage atomicity alone cannot authenticate a policy or establish that
a restored older database is the newest authorized state. A future implementation must
make authority scoping, explicit initialization, monotonically retained time/revisions,
commit-before-use ordering, concurrent updates, corruption/missing-state rejection and
backup/rollback threat assumptions testable. These are remaining implementation work,
not external gates used to declare completion. No storage winner is asserted here.

## Verification and limits

Two new trace methods and 58 related passport/evidence/bundle/federation methods pass
(the 58 include the two new methods), with zero skips. Ruff and formatting pass.
Initial Bandit scanning reports two existing B311 uses of seeded `random.Random` in
bounded mutation tests; neither generates cryptographic material. The production scan
passes without exclusions; the test scan passes with B311 excluded. The original
findings are retained, not erased. Diff checks pass. The existing workflow discovers
`test_passports.py`; no new hosted run, installed artifact or crash durability is claimed.
See [source-bound results](p16-trust-floor-v3-results.json).

Next: implement the separate authenticated policy-admission/persistence boundary in a
bounded software slice after reconciling the remaining audit inventory. Transport,
P14 measured-contract consumption and P17–P19 delivery remain unfinished. No weapon
integration, MLS/CNSA accreditation, hardware latency or availability claim is supported.
Insufficient information for tactical deployment.
