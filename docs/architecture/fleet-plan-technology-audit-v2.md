# Snapshot-bound rollout plan technology audit v2

Audit policy version: **2**. Decision: **KEEP bounded streaming I/O and native
SHA-256 through the synchronous Python adapter; add a post-journal-commit time
check.** Reviews the plan component introduced in `9d9d5f1` through
`9d8dc10f0bbd9b6dbd8ca7e0bf2a620123af788c`. This is decision six of eight;
signed wave claims and the optional fabric remain under separate review.

## Constraints first

The source is a mutable local directory containing exactly four fixed names.
Admission must reject symlinks, nonregular files, oversized members, truncation
and growth beyond the inspected size. It must bind the copied policy/artifact
bytes to the signature and journal pins. Inspection examines at most five entries;
member limits are 8192, 64, 2048 and 8 MiB bytes. Copy requests are at most 64 KiB,
with a final one-byte EOF probe. Private copies are temporary evidence, removed
before durable floor or journal updates; no artifact is executed or retained.

Deployment is a local Linux control-plane callable, with caller-owned trusted
clock/key and protected persistence directories. No throughput SLA, hard realtime,
embedded RAM target, asynchronous service or multi-host cache is specified.
Filesystem/scheduler stalls may be unbounded. Exact content binding and fail-closed
partial failure therefore dominate language throughput. Shared regular-file and
signature contracts are consumed without editing their producing modules.

## Candidate evidence and decision

Primary sources consulted 2026-10-10. These are requirement comparisons, not
claims that contenders were benchmarked or cannot implement equivalent safety.

| Candidate | Relevant evidence and assessment |
| --- | --- |
| Python bounded read/write loop with native hashing | [hashlib](https://docs.python.org/3.13/library/hashlib.html) supports incremental SHA-256; [temporary directories](https://docs.python.org/3.13/library/tempfile.html) supply private lifetime-scoped storage. Explicit remaining-byte accounting and hashing the same chunks written bind the snapshot without loading the full artifact. The executable read trace and mutation tests below verify those properties; synchronous ordering keeps cleanup and both persistence steps inspectable. |
| Rust native streaming adapter | [Rust I/O copy](https://doc.rust-lang.org/std/io/fn.copy.html) handles stream copying and may use platform acceleration. A fixed-buffer implementation with explicit length checks and incremental digest can satisfy this boundary; ownership is useful for descriptor management. It need not be a service, correcting the original document's assumption. It still needs the same snapshot, signature, expiry and cross-file failure logic; no missing native-only API or measured bottleneck establishes a material migration win. |
| C# FileStream/Stream with bounded buffers | [.NET Stream.Read](https://learn.microsoft.com/en-us/dotnet/api/system.io.stream.read?view=net-9.0) permits short reads and bounded spans. A managed adapter can implement the same exact-length loop and disposal sequence, with typed errors and buffers. Short-read handling and final time validation remain explicit requirements. A CLR host would favor this option; introducing that hosting boundary supplies no demonstrated advantage to this local callable. |
| Erlang/Elixir raw binary file I/O | [OTP file](https://www.erlang.org/doc/apps/kernel/file.html#read/2) exposes bounded file reads and raw/binary modes. BEAM supervision is credible for concurrent transfer services, but file-server/process lifecycle and supervision do not establish snapshot authenticity or atomicity across the two durable stores. This component has no distributed transfer requirement. |
| mmap in C, Rust, managed or Python hosts | Linux documents SIGBUS when accessing mapped pages beyond the file end. [mmap](https://man7.org/linux/man-pages/man2/mmap.2.html). Mapping an attacker-mutable source makes truncation a process-fault concern rather than an ordinary short-read rejection. Mapping an already-private copy is possible but does not eliminate creating that copy. No zero-copy claim is appropriate for this boundary. |
| Kernel-assisted copy/reflink followed by hash | [Python shutil](https://docs.python.org/3.13/library/shutil.html) and Rust copy expose efficient copy paths. An appropriately bounded implementation could be valid, but generic helpers do not by themselves provide the exact inspected-size/EOF and digest contract. Hashing the private destination adds a pass. Filesystem-dependent acceleration is not an integrity improvement, and no measured transfer bottleneck justifies changing this bounded path. |

KEEP favors a small synchronous control surface over native file I/O and hashing,
with explicit bounds and recoverable short-read errors. It is not a claim that
Python is faster or has stronger static types. The alternatives' plausible
advantages do not establish a missing requirement here. Installed tools, prior
familiarity and rewrite cost are excluded from the decision. A native migration
would need parity for these contracts; none is required by the current evidence.

## Executable audit and correction

Two I/O checks exercise the production copier. Truncation and growth injected
after opening the artifact both reject before either persistent store changes.
A 196625-byte synthetic artifact produces read requests
`[65536, 65536, 65536, 17, 1]`; the destination bytes and returned SHA-256 match
the fixture. Existing real-signature tests verify that later source replacement
cannot alter private-copy pins. No claim of directory-wide atomic source capture
is made: only a coherently signed private copy is admissible.

The timing audit found that journal creation could block after the last trusted
time check. Four new methods failed before correction: exclusive expiry after
journal commit, missing final observation, clock exhaustion, and six malformed
or backward final samples. The trace showed only three observations, all before
the journal existed. The corrected implementation samples once more after
initialization returns and checks monotonicity, strict integer bounds and the
unchanged exclusive expiry. The positive trace reopens the journal at the fourth
sample, establishing that the check follows persistence.

If that final sample rejects, floors and the pending journal remain committed.
This preserves evidence and prevents silent overwrite/reinitialization. Consumers
must reconcile existing state; no automatic retry is added. The fourth sample
is checked but not persisted, avoiding an endless commit/resample sequence.
The durable floor and journal retain their respective pre-commit sample values.

The plan and claim suites pass 26 methods, with Ruff/format and production Bandit
passing. Two claim fixtures were adapted to supply the extra trusted observation;
the first run exposed one missed fixture through the intended fixed plan error.
An initial late-binding lint warning in the mutation fixture was corrected by
capturing its replacement bytes explicitly. See the
[source-bound evidence record](../verification/fleet-plan-technology-audit-v2.json).

## Limits preserved

Return can still be delayed after the last sample. This is inert bookkeeping,
not lasting execution authority or a retained artifact cache. The two durable
stores are not an atomic cross-file transaction; failure may leave advanced floors
and an existing journal. A trusted local directory/process and clock/key remain
assumptions. There is no hardware, power-loss, realtime, platform-compatibility,
TUF-conformance or language-speed claim. No frozen bound was relaxed. The signed
claim adapter's own final commit timing is next in chronological review.
