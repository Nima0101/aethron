# Source observation around qualification review controls

Baseline: `36f9cdafcea71290a6e3c101f58a3be6faab486a`.
The declaration, artifact, campaign, reference, bundle and command boundaries
were reread from earliest implementation. Their bounded offline contracts and
false physical-qualification flags remain appropriate. This correction concerns
the three declaration/artifact/campaign review drivers; the remaining comparison
and measurement drivers require a separate source-observation review. It is not
completion of the lane or of product acceptance.

The drivers previously read source files only after completing their controls.
A file changed during execution could therefore receive the reported digest even
though the controls had run against earlier imported code. Historical reports
remain unchanged: their hashes identify observed source bytes, not proof of the
bytes executed. Earlier matches against Git versions do not establish execution
provenance either.

The drivers now capture their fixed source inventories before baseline execution,
repeat the observation after successful restoration, and emit the initial hashes
only when both observations match. An unreadable initial source prevents controls;
an unreadable final source or differing digest prevents JSON output. Read errors
use `review_sources_unavailable` without underlying exception text; differences
use `review_sources_changed`. Each inventory includes the observation helper.
The additive `source_observation` field is `equal_before_and_after_controls`.
Existing result fields and negative controls are preserved. Production admission,
protocol thresholds and physical-qualification flags are unchanged.

These are trusted source-checkout tools, not a file-access service. Inventory paths
are fixed in code; the helper is not an untrusted-path API. Files are read as whole
byte strings, with no new file-size or wall-clock guarantee. Observations are not
atomic across files. They do not detect edits reverted between observations,
stale modules imported before invocation, altered import resolution, unlisted
dependencies, malicious instrumentation or changes after the final observation.
Use a fresh process and a controlled checkout. This is neither hermetic execution,
an authenticated receipt, a complete dependency inventory nor a build attestation.

## Technology decision

Requirements are finite synchronous controls inside Python 3.9/3.13 processes,
fixed local source inventories, unchanged SHA-256 report fields, rejection before
report emission, and no remote service or hard deadline. There is no requirement
to build/install a new distribution or to observe arbitrary untrusted files.

| Candidate | Decisive property and limitation |
|---|---|
| Python with native `hashlib` | Directly brackets the actual in-process control lifecycle and preserves existing byte/digest semantics. Explicit before/after comparison is needed; hashing alone does not attest execution. |
| Git tree/object inventory | Identifies versioned repository objects and works well for immutable report publication. A tree identity alone cannot show that a mutable working copy or imported module executed those objects. |
| Nix derivation/build orchestration | Credible for describing build inputs and a controlled build environment. This source-checkout check does not build a product; adopting a derivation would establish a different execution protocol and still require verification of that protocol. |
| F# or C#/.NET stream hashing coordinator | Provides native SHA-256 over byte arrays/streams. It can implement equivalent observations, but an external coordinator needs an explicit handshake to bracket Python's baseline/restoration boundary. No independent-service or native-ABI requirement calls for that boundary here. |

**KEEP Python orchestration; FIX source observation.** Direct access to the tested
lifecycle, rather than installed tools, familiarity or rewrite cost, decides this
small correction. A hermetic distribution or independently attested execution
requirement must reopen the decision; it cannot be satisfied by stronger wording
on these file hashes. No cross-runtime speed claim or benchmark ranking is made.

Official sources consulted for mechanism descriptions:
[Python hashing](https://docs.python.org/3.13/library/hashlib.html),
[Git tree inventory](https://git-scm.com/docs/git-ls-tree),
[Nix derivations](https://nix.dev/manual/nix/2.34/language/derivations.html), and
[.NET SHA-256 byte/stream operations](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-9.0).
The suitability judgment is specific to the constraints above.

## Verification

Four new methods execute the real driver controls with a controlled source-reader
fault: changed bytes after baseline, missing bytes before baseline, missing bytes
after baseline, and stable-source output. They preserve real baseline/mutation/
restoration execution; no result objects are fabricated for these checks.
The RED run had twelve assertion failures and zero execution errors across all
three drivers (nine failure-boundary cases and three metadata controls).

After correction, 21 related methods pass, including prior result-category and
declaration/artifact/campaign negative controls. Initial Ruff findings were three
import-order violations and one formatting mismatch; all were corrected, followed
by a passing test rerun, Ruff check/format and targeted Bandit. Python 3.9 syntax
parsing is separate from hosted runtime execution. Fresh subprocess reports and
current source hashes are retained in [the result record](source-observation-v3.json).
The configured hosted workflow discovers the new tests and runs these drivers.
Local success is not an exact-head hosted pass or physical/product qualification.
