# C02 recorded replay qualification review — V3, partial

Decision for this pass: **CLARIFY retention, stream ownership and certification
claims; add negative evidence coverage.** Executable reader behavior is unchanged.
C01's full runtime reassessment remains open; this is an independent allowed
qualification review, not a claim that the full audit cursor has passed C01.

The `read_frames` docstring claimed retention of at most one record. The generator
keeps local variables across suspension, and the old `data` binding remains while
the next right-hand-side read is evaluated. Caller-retained frames and stream
buffers are additional storage. An 8 MiB payload limit therefore cannot be read
as an 8 MiB process or peak-memory guarantee. The docstring and historical V2
note now state these limits without changing buffering or decoding.

`read_frames` validates individual records as iteration advances. A valid first
record may be returned before a truncated or corrupted second record is read.
Previously returned frames are not retroactively revoked, and neither prefix
acceptance nor end-of-stream constitutes source authentication or physical
calibration validation. Checksums detect byte mismatch against a supplied hash;
they do not establish who supplied either value. The output remains recorded,
not current live sensor support.

The generator neither closes the caller-provided stream nor establishes an I/O
deadline. A bounded read request is not a deadline or a limit on all allocations
inside a caller-supplied stream. No cryptographic, MLS, hard-real-time, uptime or
physical-device qualification follows from this reader's tests.

The added test explicitly retrieves a valid recorded prefix, then requires
failure on both truncated and tampered suffixes. It confirms that retained prefix
metadata still says `live_evidence=False` and that the caller's stream remains
open after the generator is closed. Four focused replay test methods pass,
including existing identity/live-clock rejection and recorded provenance checks.
The new case confirms existing behavior; it is not a newly fixed decoder defect.
An AST comparison excluding docstrings verifies no executable reader change.

Primary references inspected 2026-10-10:
[Python yield expressions](https://docs.python.org/3/reference/expressions.html#yield-expressions)
document suspension with retained local state;
[binary stream reads](https://docs.python.org/3/library/io.html#io.RawIOBase.read)
describe the stream interface. These references support the ownership wording,
not a complete memory or timing proof.

The earlier Python/readinto/Node/.NET/JVM/MCAP technology comparison remains
historical evidence only. This pass performs no new implementation ranking,
throughput optimization, runtime installation or wire-format migration. The
full fresh technology reassessment is not complete. Targeting, engagement and
unauthorized-access operational integration are not qualified or implemented.
Historical T10 latency and signed radar startup failures remain retained, along
with hardware/legal/certification gates. Insufficient information for tactical
deployment.
