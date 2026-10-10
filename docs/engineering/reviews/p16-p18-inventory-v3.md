# P16–P18 review inventory v3

Snapshot: `92293281386ebafa9895dda5863be179bc41525e`, plus the probe correction
described below, reviewed 2026-10-10. This is an evidence inventory, not an architecture
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
| Task descriptions | [Review](p16-task-v3.md): KEEP bounded descriptions; no task execution or replay store. |
| Bundle verification | [Review](p16-bundle-v3.md): KEEP snapshot composition; all revocation lists rechecked. |
| Direct federation | [Review](p16-federation-v3.md): KEEP closed pinned table; no enrollment or distributed consensus. |
| Inbox resource accounting | [Review](p16-inbox-v3.md): KEEP local bounded queue; no transport or hard real-time guarantee. |
| Packaging evidence | [Review](p16-packaging-v3.md): FIX installed/source identity comparison; no full-distribution attestation. |
| Comparison and mutation probes | FIX optimized-mode evidence loss, as detailed below. |

## Missing implementation and unsupported claims

These rows cannot receive a KEEP/MIGRATE decision for code that does not exist. They
remain unfinished software or unresolved qualification requirements, not fictitious
external gates. No whole-phase completion can be inferred from the rows above.

| Scope | State at this snapshot |
|---|---|
| P16 task/federation structural schemas | Passport schemas exist; task and federation schema publication remains absent. |
| P16 transport, enrollment and persistent rollback floors | Not implemented by the owned modules. Caller-provided pins/floors are assumptions, not these services. |
| P16 cross-phase conformance | Local passport/task/bundle/federation/inbox vectors exist; integrated P2/P3/P14 consumer qualification is not established. |
| P17 common picture and operator collaboration | No owned implementation or integrated client evidence identified. |
| P17 role/authority, intent, coordination and cancellation | No owned command workflow implementation; P16 verification tasks do not implement it. |
| P17 offline synchronization and conflict handling | Local inbox and direct federation checks do not provide durable synchronization or conflict resolution. |
| P17 audit/replay and human decision support | Byte binding does not supply a durable audit history or decision-support platform. |
| P18 authorized hardware/radar/satellite/radio adapters | No owned physical adapter implementation or device qualification evidence identified. |
| P18 timestamp reconciliation and synchronization health | Caller-supplied times in P16 do not establish device clock provenance or synchronization. |
| P18 scheduling, backpressure and overload | Local inbox accounting does not establish a deterministic end-to-end processing pipeline. |
| P18 latency/jitter and hardware-in-loop evidence | No identified target hardware class, workload or retained target measurements. Desktop probe samples are insufficient. |
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
The review still requires checks of remaining comparison-output and evidence-retention
assumptions before any whole-lane audit marker is justified.

Focused outcomes and source hashes: [result record](p16-probe-v3-results.json).
