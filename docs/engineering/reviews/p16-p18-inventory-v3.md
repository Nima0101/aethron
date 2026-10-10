# P16–P18 review inventory v3

Snapshot: `009eb01fe054db5d48cec2d5298fa71e4d85aa6c`, plus inbox/federation
composition tests, reviewed 2026-10-10. This is an evidence inventory, not an architecture
approval, qualification statement or lane-completion marker.

## Implemented components

The history of the owned runtime files starts with passport admission, then evidence,
tasks, bundles, federation and inbox. Each has a current review; earlier policy-2 notes
remain historical inputs. The consumed JSON-bound helper belongs to the foundation lane.

| Component | Current evidence and decision |
|---|---|
| Parser and canonicalization | [Review](p16-parser-v3.md): FIX pre-conversion integer bound; KEEP bounded offline parser. |
| Signature, trust, expiry and revocation | [Review](p16-trust-v3.md): KEEP native crypto boundary; strengthen rejection tests and clarify provisioning limits. |
| Evidence bytes | [Review](p16-evidence-v3.md): KEEP immutable byte binding; clarify digest/privacy and qualification limits. |
| Three passport schemas and conformance | [Review](p16-conformance-v3.md): KEEP structural schema tooling; FIX positive authentication control and dependency closure. |
| Task/federation structural schemas | [Review](p16-interop-schemas-v3.md): FIX missing portable structural contracts; preserve runtime admission. |
| Task descriptions | [Review](p16-task-v3.md): KEEP bounded descriptions; no task execution or replay store. |
| Bundle verification | [Review](p16-bundle-v3.md): KEEP snapshot composition; all revocation lists rechecked. |
| Direct federation | [Review](p16-federation-v3.md): KEEP closed pinned table; no enrollment or distributed consensus. |
| Inbox resource accounting | [Review](p16-inbox-v3.md): KEEP local bounded queue; no transport or hard real-time guarantee. |
| Inbox/federation composition | [Review](p16-delivery-boundary-v3.md): KEEP primitives; ADD real-API expiry, revocation, revision-floor and close traces. Caller refresh and in-flight cancellation are not implemented. |
| Packaging evidence | [Review](p16-packaging-v3.md): FIX installed/source identity comparison and [package input coverage](p16-packaging-inputs-v3.md); no full-distribution attestation. |
| Comparison and mutation probes | FIX optimized-mode evidence loss; [response types](p16-probe-response-v3.md); [capture bounds](p16-probe-capture-v3.md); [tracing lifecycle](p16-probe-tracing-v3.md); [source consistency](p16-probe-snapshot-v3.md); [timing accounting](p16-probe-timing-v3.md); [mutation integrity](p16-mutation-integrity-v3.md); historical source-manifest correction below. |

## Missing implementation and unsupported claims

These rows cannot receive a KEEP/MIGRATE decision for code that does not exist. They
remain unfinished software or unresolved qualification requirements, not fictitious
external gates. No whole-phase completion can be inferred from the rows above.

| Scope | State at this snapshot |
|---|---|
| P16 transport, enrollment and persistent rollback floors | Not implemented by the owned modules. Caller-provided pins/floors are assumptions, not these services. |
| P16 cross-phase conformance | [Edge UNKNOWN corpus](p16-edge-conformance-v3.md) checks one published API/fixture boundary; [P2 packet cases](p16-sensor-conformance-v3.md) exercise the published decoder and P16 binding independently. Integrated P2/P3/P14 runtime qualification is not established. |
| P17 common picture and operator collaboration | No owned implementation or integrated client evidence identified. |
| P17 role/authority, intent, coordination and cancellation | No owned command workflow implementation; P16 verification tasks do not implement it. |
| P17 offline synchronization and conflict handling | Local inbox and direct federation checks do not provide durable synchronization or conflict resolution. |
| P17 audit/replay and human decision support | Byte binding does not supply a durable audit history or decision-support platform. |
| P18 authorized hardware/radar/satellite/radio adapters | No owned physical adapter implementation or device qualification evidence identified. |
| P18 timestamp reconciliation and synchronization health | Caller-supplied times in P16 do not establish device clock provenance or synchronization. |
| P18 scheduling, backpressure and overload | Local inbox accounting does not establish a deterministic end-to-end processing pipeline. |
| P18 latency/jitter and hardware-in-loop evidence | No identified target hardware class, workload or retained target measurements. Desktop probe samples are insufficient. |
| P19 enterprise product acceptance, including P19.7 Help Center | Newly assigned integration scope; no integrated installed-distribution acceptance or offline bilingual help coverage established. Software delivery remains unfinished; final qualification also depends on earlier applicable gates. |
| MLS, CNSA, five-nines and zero-SPOF claims | None established by the owned software/tests. Insufficient information for tactical deployment. |
| Targeting, weapon integration, unauthorized radio operations and durable person re-identification | Excluded; not represented as pending implementable features. Independent defensive assurance remains available. |

Repository filenames must be interpreted with their path and contents:
`docs/engineering/aethron-ecosystem/evidence/phase1/p17.json` records a phase-1
software boot/update result, explicitly without hardware qualification. It is not
evidence that the P17 command-platform scope is implemented. Peer-owned sensor, robot,
runtime and client code remains outside this lane's implementation inventory.

## Public-source discovery limits

[ATAK-CIV](https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV) and the
[Hack-A-Sat library](https://github.com/deptofdefense/hack-a-sat-library) are public
source/reference locations, not proof of AETHRON interoperability or accreditation.
The latter describes a space-document/tutorial library. No code or offensive procedure
was adopted from either during this review.

The uppercase HAVELSAN URL returned a browser error; subsequent discovery located the
[public organization](https://github.com/havelsan) and individual repositories.
[ASTERIX](https://github.com/havelsan/asterix) identifies a Java parser and lists
resources/samples. The [video framework](https://github.com/havelsan/VideoDistributionFramework)
page presents a README with empty installation, testing and license sections.
Those observations do not establish a reusable, tested or licensed implementation.
Source/rights verification remains necessary before any adoption; no operational
adapter design or performance conclusion is derived here.

## Probe evidence correction and technology decision

The comparison probe and trust mutation runner used Python assertions as evidence
gates. [Python optimization](https://docs.python.org/3.13/using/cmdline.html#cmdoption-O)
removes those assertions. In the comparison probe it also removed verifier calls inside
assertions, yet the script emitted timing fields. In the mutation runner it removed
the checks requiring unique source substitutions and actual assertion failures.

Requirements are bounded local inspection of existing Python APIs and an independent
Node primitive comparison, with no network, target qualification or throughput SLA.
KEEP Python orchestration with explicit rejection of optimized execution and KEEP the
independent Node side. Direct Python calls inspect the actual implementation under
review; Node's [strict assertion API](https://nodejs.org/api/assert.html) supplies a
separate primitive check. Java with [JUnit](https://docs.junit.org/current/user-guide/)
is a credible alternative test ecosystem, but replacing this driver with it would
still require Python execution to inspect these APIs; an additional orchestrator does
not remedy the evidence defect. This is not a claim of superior Python performance.
The compiler/interpreter mode is now checked explicitly before either probe performs
its work. Missing optional crypto cannot be mistaken for a successful comparison.

Real `-O` and `-OO` child processes initially returned success for each script: four
retained assertion failures across two test runs. Both scripts now reject those modes
with no JSON evidence output. Normal executions remain independently checked. Workflow
path filters now include both Python and JavaScript passport probe files.

This corrects tooling evidence; production passport admission and frozen thresholds are
unchanged. Existing samples are not retrospectively upgraded into qualification. The
original policy-2 audit gets a historical-status note linking this current inventory.
The subsequent response and capture reviews above correct those boundaries. Their
limits remain explicit; this inventory does not turn missing software into completion.

Focused outcomes and source hashes: [result record](p16-probe-v3-results.json).


## Source evidence reconciliation

The capture bridge was checked against all four requested file hashes and its parent.
Seventy-seven source-hash entries from ten retained P16 result records match the Git
commit that first published each record. These are historical byte-identity checks,
not fresh execution of every historical experiment; they do not authenticate authors
or prove current deployment parity. Existing result files remain unchanged.

Two new tests exposed incomplete standalone manifests: the comparison report had only
a fixture digest, and the mutation report omitted the consumed JSON-bound helper and
vector file. Both tools now emit five explicit project-file digests. The comparison
covers its Python driver, Node script, passport verifier, JSON-bound helper and vectors.
The mutation report covers its driver, test module, passport verifier, helper and
vectors. These are listed direct project inputs, **not dependency closure**: package
initialization, standard libraries, installed crypto/native libraries, interpreter and
Node executables are not hashed by this manifest. Files are read after execution;
there is no atomic snapshot, loaded-bytecode attestation or change-during-run defense.
The reports carry that limitation beside the digests.

Technology decision: KEEP native-backed standard SHA-256 in the existing driver.
The constraint is portable metadata for a small fixed list of trusted local files,
with no throughput target or claim of whole-environment provenance. Python
[hashlib](https://docs.python.org/3.13/library/hashlib.html), Node
[createHash](https://nodejs.org/api/crypto.html) and Java/Kotlin
[MessageDigest](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html)
all provide appropriate digest APIs. Java/Kotlin is a credible option outside these
tools' current languages. Moving the metadata pass to another runtime gives no
additional snapshot or attestation property; a complete signed provenance system
would be a different requirement. This is a constraints-based choice, not a measured
speed ranking or a preference based on installation or rewrite cost.

Fresh comparison output now labels the active audit policy as version 3. Two retained
assertions exposed the stale version-2 field; historical reports retain their original
versions. Together with the two manifest failures, all four new assertions now pass.
Current outcomes and the historical source-match inventory are retained in the
[source reconciliation record](p16-probe-provenance-v3-results.json).

That source-manifest correction concerned assurance tools only. Its bridge commit
`8edce6f5e6cd877b2c836da14a1947f7f06a984f` has now been verified against its parent,
five recorded file hashes and noreply identity. No audit or phase completion marker is issued.

The task/federation structural publication gap identified above in earlier snapshots is
now corrected locally. This does not establish integrated cross-phase consumer conformance.

The comparison driver now rejects changes visible between its initial and final reads
of the five listed files, and hashes the captured fixture bytes it parsed. See the
[source consistency review](p16-probe-snapshot-v3.md) for remaining race, loaded-code
and dependency limits. The historical post-execution-only behavior above remains a
record of the earlier implementation; the trust mutation runner is unchanged here.

The mutation runner now also captures listed source bytes, rejects observable changes,
and requires the four selected baseline methods to pass before crediting guard-removal
failures. The [mutation integrity review](p16-mutation-integrity-v3.md) records remaining
loaded-code and isolation limits; the earlier post-execution-only behavior is historical.
