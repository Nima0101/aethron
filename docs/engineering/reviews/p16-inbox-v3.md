# P16 bounded inbox review v3

Baseline: `349781babb93685dfc281a5f45ea7aae87d15ea8`. Reviewed 2026-10-10.
Decision: **KEEP bounded deque with explicit lock; FIX coverage; CLARIFY lifecycle claims**.
No production code or portable trace bytes changed.

## Constraints and technology review

The existing primitive is process-local storage for public/synthetic software artifacts:
at most 16 immutable byte entries, 1 MiB aggregate payload, 64 KiB per entry, peer-count
quotas, caller-clocked expiry, reject-incoming overload behavior, and terminal close.
It is not a transport, authenticated peer registry, scheduler, control loop or P18
real-time queue. There is no target hardware, measured contention requirement or lock
latency budget. Correct atomic accounting and explicit ownership are decisive.

| Candidate | Source-bound properties and fit |
|---|---|
| Python deque with Lock | [Lock semantics](https://docs.python.org/3.13/library/threading.html#lock-objects) serialize the critical section, but do not promise waiter ordering or bounded waiting. One lock covers count, bytes, peer quota, expiry and close. Exact immutable payloads prevent caller mutation through the supported API. |
| Rust crossbeam-channel | [Bounded channels](https://docs.rs/crossbeam-channel/latest/crossbeam_channel/fn.bounded.html) bound queued message count. Aggregate byte and peer limits plus removal of expired entries behind a live head still require a coordinated admission/lifecycle design. Ownership is valuable for a native consumer; count capacity alone is not contract parity. |
| C# System.Threading.Channels | [Bounded channel documentation](https://learn.microsoft.com/en-us/dotnet/core/extensions/channels) specifies waiting/dropping behavior and nonblocking TryWrite semantics. Those are credible building blocks; this profile's byte/peer accounting and arbitrary expiry still need explicit coordination. |
| Erlang/Elixir processes | [Erlang process documentation](https://www.erlang.org/doc/system/eff_guide_processes.html) describes message transfer and mailbox behavior. Process isolation is credible for independently supervised workers. A mailbox alone does not enforce this primitive's total-byte and per-peer admission policy; ingress must be bounded before queuing. |

KEEP the current small synchronous design: all required accounting is in one explicit
critical section, with no worker or secondary queue. The alternatives are credible, but
none demonstrates a material win for this fixed local contract on present evidence.
No comparative speed ranking or native-hardware qualification is inferred. Installed
tooling, incumbent preference and rewrite effort are not selection criteria. Concrete
native/real-time requirements need a separate decision and target evidence; this review
only verifies lifecycle/claim boundaries and does not optimize an operational path.

## Findings and verification

Eight baseline inbox tests passed, including its existing two-producer capacity test.
Three added tests retain behavior omitted from the prose:

- a rejected empty-payload put still purges expired entries and advances the trusted-time
  floor; a subsequent earlier time closes the inbox;
- closing after dequeue does not erase a caller-held payload, while subsequent takes
  return no payload and the closed inbox reports zero queued bytes;
- a put with a rollback clock clears queued entries and permanently closes without
  retaining or returning the incoming payload.

The retained result test also proves that `repr=False` does not redact dataclass
serialization: `asdict` contains payload bytes. Logical queued-byte counts exclude
previously dequeued caller-held objects. Close is a queue lifecycle operation, not a
consumer cancellation or memory-erasure mechanism.

The old phrase “short state lock” did not establish an execution-time bound. Documentation
now explicitly states that lock acquisition, including close, can block without a timeout.
The supplied timestamp is not refreshed after waiting. Existing count/byte bounds prove
neither RSS bounds nor a physical deadline. No production defect was demonstrated; the
new cases pass the unchanged implementation, so no production RED/fix is claimed.

Reproduce with the pinned conformance environment:

```sh
python -m unittest discover -s tests -p test_interop_inbox.py -v
python -m unittest discover -s tests -p 'test_interop*.py'
```

[Source bindings and results](p16-inbox-v3-results.json) retain the executed checks.
No hardware, MLS, CNSA, availability or real-time qualification follows. The runtime
modules have been reviewed individually; packaging/workflow and phase inventory claims
still need reconciliation before the audit catches up to HEAD. No completion marker.
Next: P16 packaging/workflow and remaining phase inventory review.
