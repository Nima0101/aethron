# P2.1 working-copy evidence provenance — V3 supplement

Decision: **CLARIFY immutable source retrieval for C08 and C09 reviews.** The
original reports explicitly identify three reviewed files as working copies.
Those files were not added or updated by the local review commits. A reader
therefore cannot assume that every source hash describes that commit's tree.
The reports did not identify an immutable retrieval reference for these copies.

All three recorded hashes match the corresponding public files at protected
main commit `a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46`:

| Review | Source | Meaning |
|---|---|---|
| C08 inspection | `integrations/edge/aethron_edge/sensors/recording_io.py` | Working-copy bytes match the published source |
| C08 inspection | `integrations/edge/aethron_edge/sensors/cloud_inspect.py` | Working-copy bytes match the published source |
| C09 appliance | `integrations/edge/aethron_edge/sensors/provisioning.py` | Working-copy bytes match the published source |

The [supplemental binding record](evidence/phase2/working-copy-provenance-v3.json)
pins the two original report blobs to their public delivery commits, and these
three source blobs to protected main. It preserves their original hashes and
working-copy notes. It does not substitute current HEAD for historical evidence,
or change the source files. Both original report blobs and all three source
hashes were checked using `git show <commit>:<path>` and SHA-256. A checkout is
unnecessary; verification does not execute the source.

For example, with the recorded public Git objects available locally:

```sh
git show a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46:integrations/edge/aethron_edge/sensors/recording_io.py | sha256sum
```

Source equality identifies bytes; it does not authenticate test execution or
prove that an arbitrary later checkout has equivalent behavior. No new runtime
test, installed-package reproduction, boot soak, hardware measurement or
technology comparison is claimed. Existing failures and qualification limits
remain unchanged. This supplement resolves these three retrieval references;
it does not complete the full V3 reassessment, whose cursor remains C01.

## C01 historical packet report retrieval

The C01 V2 report records four source hashes without an immutable retrieval
reference. The prior timing review checked those hashes against the original
local review commit; this supplement additionally binds them to public delivery
commit `7f2d87abcceea0592da587d371a2f8924d7c0cd8`. At that commit, the report
bytes and all four source files match the retained hashes. The sources are the
packet module, packet tests, comparison harness and Node comparison worker.
The supplemental JSON records each path and digest under
`historical_packet_binding`; later harness revisions must not be substituted.

This verifies retrieval of the report's final source snapshot. It does not bind
the three superseded experiments to their earlier source snapshots, recover raw
timing samples, authenticate execution, or show which code was loaded during a
historical run. Those limits remain open. The original report is unchanged,
including the mixed-width alternative advantage, omitted worker pipe-I/O CPU,
shared-host timing and previous latency/startup failures. No new benchmark,
production change or fresh KEEP/MIGRATE decision is included.

## C02 historical replay report retrieval

The retained replay report and its four source hashes match public delivery
commit `413791f79e9239dc67341e727047a11574b1eb5c`. The sources are the replay
module, replay tests, I/O comparison harness and separate stock-JSON parser
counterexample. `historical_replay_binding` records the report digest and source
map. This supplies the missing public retrieval reference without editing the
historical report or substituting the current harness.

The source snapshot is the final implementation. It does not establish the
source bytes used for the report's `before` observations, authenticate either
run, or recover individual timing samples. The stock-parser counterexample is
not a complete alternate replay implementation. The recorded fragmented-input
advantage for `readinto`, tracing-versus-RSS distinction and previous failures
remain unchanged. No timing or whole-replay qualification is added.
