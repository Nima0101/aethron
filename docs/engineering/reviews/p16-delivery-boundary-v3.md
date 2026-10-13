# P16 inbox-to-federation boundary review v3

Baseline: `009eb01fe054db5d48cec2d5298fa71e4d85aa6c`, reviewed 2026-10-10.
Decision: **KEEP the separate bounded primitives; ADD integration coverage**.
No production defect or production RED/fix is claimed.

The parser, signature/trust, evidence, task, bundle, federation and inbox source was
re-read in implementation order. This slice checks composition of the last two
boundaries, which previously had separate tests. It does not complete the whole-lane
technology review or implement a delivery service.

## Constraints and technology decision

The deployed contract under inspection is a synchronous, process-local FIFO for
immutable software-artifact bytes, followed by explicit offline verification. Queue
time is caller-provided milliseconds; verification time is caller-provided seconds
in a separate domain. No clock conversion, trusted-clock acquisition, configuration
refresh, task execution, hardware latency budget or network transport is implemented.
Tests must exercise the actual public APIs, with real fixture signatures, bounded
inputs and explicit failure outcomes. No sleep, hardware or remote service is needed.

KEEP Python unittest for these finite contract traces. Its documented
[fixtures and assertion methods](https://docs.python.org/3.13/library/unittest.html)
support direct calls and explicit negative checks without optimization-sensitive
bare assertions. [Hypothesis state machines](https://hypothesis.readthedocs.io/en/latest/stateful.html)
are credible for generated action sequences and shrinking, but these four cases need
specific boundary times and trust replacements, not a generated search. A JVM runner
using [JUnit](https://docs.junit.org/current/user-guide/) is a credible alternative
outside the implementation language, but would need a process/serialization adapter
to exercise these process-local Python objects. That would test a new boundary rather
than directly inspect the current one. No material migration advantage is established
for this narrow verification requirement; no speed or memory ranking is claimed.
The previous component-specific native/channel/policy alternatives remain relevant
to future deployment requirements, not evidence of a qualified runtime here.

## Executable findings

`tests/test_interop_delivery.py` uses the existing portable federation corpus and
the real inbox and verifier. Four tests establish:

- A still-retained queued envelope rejects exactly at federation expiry, despite a
  longer inbox deadline. The initial valid result remains an immutable snapshot.
- Updated, repinned revocation inputs reject the same previously queued envelope.
  Supplying the old policy still authenticates it: configuration freshness is a
  caller responsibility, not an inbox property.
- A newly supplied federation revision floor rejects the queued old snapshot.
- Closing the inbox clears its queued copy and prevents delivery. It neither erases
  nor revokes an already returned copy; that copy still authenticates against the old
  current fixture configuration.

Every federation rejection is checked for absent digests, revisions, expiry and
evidence, with authority flags false. The positive control retains the original
passed/failed/unknown evidence outcomes. Missing crypto causes a failing positive
control, not a skip. These tests pass unchanged production code, so there is no
fabricated failing baseline or runtime correction. They do not supply atomic
configuration refresh, durable revocation floors, secure erasure or cancellation of
in-flight consumers. Those missing services remain software work.

The existing workflow's `tests/test_interop*.py` filter and discovery include this
file. Local results: 96 related methods PASS, zero skips; Ruff check/format and Bandit
PASS. This is local evidence, not a hosted-CI or installed-release claim.

```sh
PYTHONPATH=tests:. python -m unittest test_passports test_passport_evidence \
  test_passport_schemas test_interop_tasks test_interop_bundles \
  test_interop_federation test_interop_inbox test_interop_delivery -v
```

[Source-bound results](p16-delivery-boundary-v3-results.json) retain the test log digest.
The cached `origin/main` is `a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46`;
fetch failed because `FETCH_HEAD` is read-only. No fresh-main reconciliation is claimed.
Next review boundary: P16 installed-package execution and consumed P2/P3/P14 contracts.
P17–P19 implementation and qualification remain incomplete. Insufficient information
for tactical deployment.
