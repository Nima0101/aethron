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
