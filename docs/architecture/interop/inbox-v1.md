# Bounded offline inbox v1

This process-local resource primitive holds opaque verification inputs. Enqueue is
not authentication, scheduling authority, execution permission or evidence truth.
Consumers must run the current public bundle/federation verifier after dequeue.
Only public or synthetic software artifacts belong here; it is not a person-history store.

## Technology decision

Constraints: Linux/macOS/Windows, synchronous producers/consumers, at most 16 entries,
1 MiB retained payload, 64 KiB per entry, per-peer count limits, reject incoming on
saturation, explicit expiry, no background threads, disk or network. No target hardware
or hard real-time requirement applies to this offline P16 boundary.

Compare [Rust crossbeam bounded channels](https://docs.rs/crossbeam-channel/latest/crossbeam_channel/fn.bounded.html),
[.NET bounded channels](https://learn.microsoft.com/en-us/dotnet/core/extensions/channels),
[Erlang process mailboxes](https://www.erlang.org/doc/system/eff_guide_processes.html),
and [Python deque](https://docs.python.org/3/library/collections.html#collections.deque)
with an explicit [lock](https://docs.python.org/3/library/threading.html#lock-objects).
Channels provide count bounds and blocking/overflow choices; aggregate bytes, peer
quotas and expiry require additional atomic accounting in each option. Erlang isolation
is attractive for distributed workers, but a mailbox alone is not the required bounded
admission policy. Rust is a strong candidate for a future native hardware path; its
ownership advantage does not establish a material win for exact immutable Python bytes
at these small limits. Select Python's native deque plus one explicit lock: payloads
cannot mutate, all quota/expiry updates share a critical section, and there are no hidden
worker queues or asynchronous producers. No speed superiority, lock fairness, hard
real-time, RSS bound or P18 hardware qualification is claimed. Reopen selection for
native deployment or measured contention. Capacity and lifecycle contract tests are the
decisive executable evidence, not interpreter availability or existing language usage.

## API and frozen bounds

`BoundedInbox(max_items=16, max_bytes=1048576, max_per_peer=16)` accepts exact positive
integers no larger than these ceilings; per-peer count cannot exceed total count.
`put(peer, payload, *, now_ms, expires_at_ms)` requires a caller-assigned software peer
alias, exact immutable nonempty bytes <=65536, and an exclusive deadline at most 60000ms
ahead. Times are safe integers from one caller-trusted monotonic clock, not UTC passport
timestamps. Transport callers must authenticate peer aliases before using quotas.

`take(*, now_ms)` returns the oldest unexpired entry or an empty result. Every call
first validates monotonic time, purges *all* expired entries (including behind a live
head), then applies quotas or takes one item. Equal timestamps are valid. Invalid time
or rollback clears held references and permanently closes the inbox; recovery requires
a new instance and an independently trusted clock. `close()` clears references and is
idempotent. No physical memory-erasure guarantee is made.

Full queues reject incoming entries without dropping older live entries. Rejected
payloads are not retained. Invalid peer/payload/deadline returns a fixed error. Reports
include current item/payload-byte counts; only successful `take` includes payload and
peer. All reports have `execution_authority=false`, `motion_authority=false`, and
`evidence_verified=false`. This is logical retained-byte accounting,
not an allocator/RSS or systemwide rate limit. At most 16 entries are inspected per call.
Capacity operations do not wait for free capacity; the short state lock can contend.
Concurrent calls are serialized by lock acquisition, without a fairness guarantee.
Expiry is checked at admission/dequeue; an idle instance does not run a purge timer.
