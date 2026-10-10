# Verifier input boundaries

The developer verifier requires Python 3.9+ and the verification-only parser in
`requirements-links.lock`. The core runtime package does not gain this dependency.
For offline installation, prepare a wheelhouse with `python -m pip download
--only-binary=:all: --require-hashes -r requirements-links.lock -d link-wheels`
on a connected machine, then install with `python -m pip install --no-index
--find-links link-wheels --require-hashes -r requirements-links.lock` offline.
Use the same interpreter for installation and verification. Missing parser imports
fail with this installation instruction; no automatic download or regex fallback.

Both checkers parse CommonMark inline/reference links and images, excluding code,
raw HTML attributes, remote schemes/authorities and fragment-only destinations.
Entities and percent escapes are decoded once. Queries/fragments are not paths.
A link check neither fetches its destination nor approves its content or rights.
Excess parser nesting fails explicitly instead of silently omitting links.
See [parser decision](../decisions/0024-markdown-parser-resources.json).

The public-tree checker resolves the requested immutable tree without replacement
objects or lazy fetching. It rejects repository-selecting environment overrides,
missing objects, invalid UTF-8 and symlink Markdown. It admits 10,000 entries,
1,000 Markdown paths, 1 MiB per document, 16 MiB total document bytes and 10,000
local destinations. Missing-report source/target fields admit 1 MiB of summed
UTF-8 bytes, excluding JSON overhead. Invalid/incomplete scans exit2 with
`invalid_public_tree` and no partial report. Complete reports retain exit0/1.

The worktree verifier rejects optimized Python execution, mismatched repository
roots, selected Git environment overrides, escaping paths and symlink/reparse
entries. Its existing discovery rules exclude generated directories only when
untracked and require coverage of selected tracked text. Filesystem errors fail
the scan. These checks assume a stable trusted checkout, not a hostile concurrent
filesystem. Freeze manifests remain trusted declarations, not signed provenance.

The worktree public-content Markdown scan has separate limits: 1,000 documents,
1 MiB each, 16 MiB total and 10,000 local destinations. Empty/untracked selected
documents and repeated destinations count. Oversized files are rejected before
opening when stat establishes their size. Otherwise a bounded binary read permits
one extra byte to detect excess before decoding/parsing. Excess raises
`worktree_markdown_limit`; later product checks and the final PASS are not reached.
See [admission decision](../decisions/0025-worktree-markdown-admission.json).

Freeze payload hashing now reads at most 64 KiB per call until EOF, preserving
exact SHA-256 comparisons and historical AGENTS mappings. I/O failures stop
completion and close the stream. This bounds input allocation for the hash loop,
not total bytes processed, RSS or time. See the
[streaming decision](../decisions/0026-freeze-streaming.json).

Manifest admission v1 accepts at most 1 MiB per fixed manifest and 10,000 file
entries. A bounded read with one extra byte catches growth after stat. The root
and `files` must be objects; names must be nonempty and digests must be 64 lowercase
hexadecimal characters. Duplicate decoded keys anywhere in the document are
rejected, including metadata and escaped spellings. Complete inventory shape is
checked before payload reads. Existing path checks still apply at payload access.
Empty inventories and other metadata values remain permitted; metadata semantics
and manifest authenticity are not verified. Excess raises `freeze_manifest_limit`;
duplicates or malformed inventory raise `invalid_freeze_manifest`. Syntax, UTF-8
and I/O failures also stop completion. The entry cap is applied after parsing;
objects, metadata and parser allocations add memory beyond admitted input bytes.
These are developer admission limits, with no change to frozen product thresholds.
See the [manifest decision](../decisions/0027-freeze-manifest-admission.json).

Git capture uses a 30-second per-command wait budget and 16 MiB stdout cap, discards
stderr and never accepts partial output after failure. It kills/reaps its direct
child; spawning/reaping are not hard-bounded and descendants retaining pipes can
outlive cleanup. No generic process-tree containment is claimed.

These are admission limits, not total RSS, CPU, filesystem or whole-verifier
bounds. Decoded text/parser allocations are additional. Source reads, other content
reads and traversal have separate admission limits below. Product child processes
remain outside these input budgets. The source syntax rules do not prove runtime security or
termination. The final PASS names completed checks, not production qualification.

The dedicated Markdown workflow exercises Linux/macOS/Windows and Python3.9/3.13.
Workflow existence is not hosted evidence. ADR source revisions identify local
pre-change baselines; source hashes bind the described files. Historical local
results do not qualify a different delivery head or platform.

Source/text admission v1 limits source input to 1 MiB per file and 16 MiB total;
other selected non-Markdown text to 8 MiB per file and 64 MiB total. A shared
counter admits 100,000 directory entries across source and content scans, including
excluded entries and repeated visits. Depth beyond 64 relative to each scan root
fails instead of pruning required coverage. Byte checks precede decoding. These
limits do not bound AST allocations, filesystem latency or whole-process memory.
See [scan admission](../decisions/0028-worktree-scan-admission.json).

The five developer child commands run sequentially with the selected interpreter,
literal argument lists and the checkout working directory. Nonzero status, launch
errors and interruption prevent the final PASS. There is no child deadline or
process-tree supervisor; a hanging child may indefinitely delay local completion.
The launcher review uses intercepted children and does not qualify Windows process
quoting or signal delivery. See [child review](../decisions/0029-verifier-child-review.json).
