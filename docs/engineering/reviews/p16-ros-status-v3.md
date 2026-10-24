# P16 consumption of published ROS diagnostic status — review v3

Reviewed 2026-10-10 at `828943affeeb6d5878dc9e07accf46571791604b`.
The preceding sensor-encoding bridge was verified against its parent, five exact file
hashes and noreply identity, then published to PR #35. A fresh main fetch succeeded;
its revision remains `a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46`.

## Scope and decision

The earliest passport parser, signature/policy, evidence, task, bundle, federation and
inbox source were re-read. Their offline, caller-clocked and non-authorizing limits
remain material. This slice addresses the next consumer coverage gap: P16 had packet
and edge-UNKNOWN fixtures but no direct check of published ROS diagnostic status.
No production defect or completed whole-lane review is claimed.

Constraints: deterministic dictionary replay with tiny synthetic payloads, direct calls
to the published API, no ROS installation, transport, device, synchronization service,
sensor inference or control. Expected diagnostic outputs must be independent of the
producer and remain UNKNOWN even when a signature authenticates their bytes.

KEEP Python direct-API conformance with portable JSON vectors. Standard
[unittest](https://docs.python.org/3/library/unittest.html) supports explicit assertions
and shared setup. This allows state transitions and the actual native-backed signature
verifier to be exercised together without translating the producer implementation.
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/)
is a credible declarative alternative outside this consumer's language, but its data
constraints cannot substitute for calls that mutate the actual ingress state and
verify signatures. A Java/JUnit driver would also need a bridge to these Python APIs.
The earlier [edge comparison](p16-edge-conformance-v3.md) records the JavaScript/Ajv
alternative for structural validation; structural checks alone do not meet this
behavioral requirement. Selection is based on the test boundary, not installed tools,
familiarity, rewrite cost or a measured performance ranking. No P18 runtime language
is selected by this decision.

ROS [clock design](https://design.ros2.org/articles/clock_and_time.html) distinguishes
system, steady and ROS time, including simulation and backward jumps. The fixture does
not compare host-monotonic nanoseconds to passport UTC seconds. A successful evidence
binding does not check whether the original observation or diagnostic is still current.

## Executable correction

Three consumer methods initially failed on the missing corpus, with zero errors. The
new separate v1 corpus contains four manually specified status snapshots: idle,
receiving, lost and invalid after a duplicate acquisition timestamp. The tests replay
the actual `RosIngress` and compare every output byte with these expectations.
An unmapped observation has no capture timestamp and never claims live evidence.
Duplicate acquisition time clears pending delivery and returns a clock fault.

Each snapshot has an independently framed signature using the existing public RFC 8032
test signer. Evidence remains synthetic with outcome `unknown`; P16 returns no motion
or evidence qualification authority. The receiving snapshot can be cryptographically
bound, just as lost and invalid snapshots can. Altering qualification, scene state or
expiry while reusing its signature is rejected with no evidence or result metadata.

Nine directly imported project source files are pinned and matched against fetched
main during fixture generation. The consumer asserts those exact pins and the loaded
ROS module path. This is not dependency closure, import isolation or loaded-bytecode
attestation. No peer-owned file is edited. CI now runs both consumer modules and
triggers on the newly consumed producer paths. Workflow existence is not hosted
execution evidence.

## Evidence and remaining work

Ten consumer tests plus 34 passport/evidence tests pass without skips. Ruff, format,
Bandit, actionlint and diff checks pass. Retained RED failures establish missing
coverage, not a demonstrated production failure. Source and log hashes are in the
[result record](p16-ros-status-v3-results.json). The generation script is retained
locally and hashed there; shipped tests require only the static public corpus.

This consumes a P3-related published dictionary/API boundary; it does not qualify ROS
messages, DDS transport, endpoint authorization, clocks, calibrated physical sensors,
watchdogs, target latency or availability. The P14 measurement-result interface remains
unidentified in fetched main. Existing filenames under `evidence/phase1` do not create
that interface. A producer handoff remains open while independent P16 work continues.
P17/P18/P19 software and release acceptance remain unfinished. No MLS, CNSA, vendor
compatibility, weapon integration or tactical accreditation is inferred.
Insufficient information for tactical deployment.

Next earliest unreviewed boundary: P16 transport and persistent trust-floor requirements,
including whether a published P14 measurement contract can be consumed without
creating a competing producer implementation.
