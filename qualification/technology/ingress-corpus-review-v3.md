# Ingress experiment corpus integrity — review v3

Baseline: `9277fb2ab4830247741fb522ecad8b10248fd937`. The fresh P4/P15
read returned to declaration/artifact validation and bundle composition, then
examined the review drivers, source observations, measurement helper, ingress
comparison and Node probe. This correction concerns the experiment's input
inventory; it does not change production admission or complete the lane audit.

Before correction, a stable but changed vector file could produce a normal
experiment report. The baseline Node probe reported `parity: true` for an empty
array, for deletion of all four duplicate-key cases, and for changing those four
expected rejections to acceptance. Python export and comparison also accepted
these changed corpora; its separately collected semantic requests did not prove
that the curated ingress vectors were present. Before/after file hashes detect
changes during a run, not replacement before a run. Historical evidence remains
unchanged; this finding does not imply its recorded corpus was replaced.

## Requirements and decision

These tools must run the exact reviewed v1 corpus: 18 synthetic cases in 18,962
bytes. The offline source-checkout experiment must preserve input bytes, expected
negative outcomes and request order. It has no user-extensible corpus, network,
device, persistent service, hard deadline or authentication requirement.

| Candidate | Decisive property |
|---|---|
| Pinned SHA-256 in Python and Node using native hash APIs | Checks all original bytes, expectations and ordering before interpreting the corpus. Both runtimes directly control their experiment's admission point. |
| Explicit ID inventory and field checks | Detects omission and malformed shape, but not replacement of a payload or an expected finding unless those are independently pinned too. |
| CUE constraints | Suitable for an extensible structured corpus. Shape/relationship validation alone does not establish equality to these exact reviewed bytes. |
| F#/C# byte-hash coordinator | Can check the same digest. Checking outside each consumer would require binding the checked bytes to what each consumer subsequently reads; it offers no stronger property for these fixed local tools. |
| Git object check | Identifies a published object. The experiment consumes working-file bytes, so checking the object alone does not bind the actual input. |

**KEEP Python orchestration and the Node experimental subject; FIX corpus
admission using a pinned digest.** The Node runtime is the behavior being measured;
replacing it would change the experiment. The Python comparator directly invokes
its semantic oracle. This decision follows byte identity and experimental scope,
not installation, familiarity or rewrite cost. It does not recommend Node for
production parsing: its four duplicate-key failures remain visible.

Sources inspected 2026-10-10: [Python hashing](https://docs.python.org/3.13/library/hashlib.html),
[Node hashing](https://nodejs.org/api/crypto.html#cryptocreatehashalgorithm-options),
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/),
[.NET byte hashing](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-9.0),
[Git tree objects](https://git-scm.com/docs/git-ls-tree), and
[ECMAScript every](https://tc39.es/ecma262/multipage/indexed-collections.html#sec-array.prototype.every).
The suitability comparison is this review's analysis.

## Behavior and evidence

Both consumers now require corpus SHA-256
`a62278050b822b70a4d40dd37aa51899ccc49ef5b94f1d2b4ff259299193aeff`
before JSON parsing. Mismatch raises `invalid_ingress_corpus`, with no request
export or report. Python also stops before collecting semantic requests. The
existing final source-observation checks remain in place. Corpus bytes are
unchanged; extensions require a versioned corpus and reviewed consumer pins.

Five changed corpora cover empty, missing, duplicate, rewritten-byte and erased
negative-expectation inputs. Two test methods first produced 15 assertion failures
and zero errors: ten Python export/comparison cases and five actual Node processes.
Python tests substitute only reads of the corpus path and use synthetic responses;
Node tests execute disposable copies. After correction, eight ingress/Node methods
and 38 related methods pass. Actual Node positive controls retain all 18 cases and
exactly four known mismatches. The existing CI already invokes these methods;
hosted success is not claimed. [Recorded results](ingress-corpus-review-v3.json)
include the baseline observations and source hashes.

Ruff, formatting and the comparator/portable-test Bandit scan pass. The Node test
scan retains seven low findings (B404, three B603, three B607); five predate this
change and two concern its new subprocess call. Reviewed calls use fixed Node
arguments, no shell, trusted tool PATH, disposable copied scripts and a 15-second
timeout. No finding is suppressed or presented as a clean whole-test scan.

Pins in trusted source are consistency checks, not signatures or protection
against coordinated edits to source and corpus. Fixed files are still read in
full; this change adds no hostile-file size or time guarantee. Two file observations
do not prove loaded-code identity. No physical, procedure, domain, target-latency,
cryptographic-certification or installed-product qualification follows.
