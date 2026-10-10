# Robotics implementation reassessment v2 — in progress

This is a historical v2 record. The [incomplete v3 review](robotics-review-v3.md)
records later hosted execution and evidence-integrity corrections. Preparation-time
status and test counts below are not current-head qualification or audit completion.

This audit starts from published checkpoint `2c206c4`, which contains the earlier
robotics components, and follows additions through `c665db7`. Publication history
is squashed before that checkpoint; it does not establish the internal creation
order of those earlier files. Within that checkpoint, audit dependency order is
decoder, signing/storage, worker, provisioning/boot authority, then ROS SDK
execution. Existing choices receive no automatic KEEP decision.

## Inventory and cursor

| Component | Implementation boundary | State |
| --- | --- | --- |
| Passive MAVLink decoder and single-datagram receiver | `telemetry/mavlink.py` | **Current: decision pending; executable comparison below** |
| Signing and persistent replay | `telemetry/signing.py` | Pending |
| Worker lifecycle and aggregate IPC | `telemetry/worker.py` | Pending |
| Telemetry provisioning and boot authority | `telemetry/provisioning.py`, `telemetry/boot_authority.py` | Pending; inspect independently |
| ROS installed SDK/DDS execution | `integrations/edge/ros2/`, `scripts/edge_ros2_check.py`, `tests/ros2/` | Pending; consume P2 sensor public interfaces, no competing sensor implementation |
| Versioned multi-packet ingress and snapshot repair | `telemetry/datagram_v1.py` | Pending |
| Finite aggregate diagnostic | `telemetry/diagnostic_v1.py` | Pending |
| Pinned hosted ROS image acquisition | `scripts/edge_ros_image_v1.py` | Pending |

`telemetry/` means `integrations/edge/aethron_edge/telemetry/`. P3.2 vendor SDK
adapters and P8 simulated robot interfaces have no implementation added by this
lane to reassess yet. Their dependencies and rights remain separate. This is an
inventory, not an audit-completion marker; the cursor has not advanced past the
first component, and forward feature expansion remains deferred.

## Component 1 constraints

Deployment is an optional Linux process, presently x86_64 software fixtures with
an ARM64 ROS tuple elsewhere. No microcontroller, hard-real-time, hardware or
physical acquisition claim. Accept only common-dialect MAVLink 2 ATTITUDE and
LOCAL_POSITION_NED; reject unknown flags, extra payloads, nonfinite values and
untrusted sender tuples. At most 280 bytes per packet and two latest samples;
100 ms receipt TTL with clock-fault latching. No transmit path, resynchronizing
stream buffer, payload history, dynamic remote configuration or perception
authority. A replacement must preserve these semantics and compose with the
separate signed replay boundary, without interpreting receipt time as capture
time. Independent memory bounds, startup and scheduler behavior matter alongside
steady-state throughput. No numerical hardware/RAM budget is invented here.

## Ecosystem discovery, 2026-10-10

Sources are primary project documentation; their capability claims are not
qualification of this implementation. No candidate is rejected for being absent
from the development host or for requiring a rewrite.

| Candidate | Evidence and decisive question |
| --- | --- |
| Generated C / C++11 | [MAVLink project catalog](https://mavlink.io/en/#language-generator-list) identifies C as the reference implementation and lists v2/signing support for both. Direct bounded parser is attractive for allocation/throughput; memory safety and complete state/replay parity must be demonstrated. Executed C experiment below. |
| Rust / rust-mavlink | [Maintained project](https://github.com/mavlink/rust-mavlink) separates core, generator and transport features, including signing and embedded/std modes. A memory-safe native candidate; investigate a decoder-only feature closure and exact strict-framing/replay behavior rather than the transmit-capable connection example. Not benchmarked yet. |
| JavaScript NextGen / TypeScript | The catalog lists v2/signing for NextGen; [ArduPilot node-mavlink](https://github.com/ArduPilot/node-mavlink) provides TypeScript packet tools and stream parsers. Bounds, stream recovery, integer timestamp precision, event-loop delay and memory need explicit checking. No network convenience class is acceptable as-is. |
| Kotlin Multiplatform | [mavlink-kotlin](https://github.com/divyanshupundir/mavlink-kotlin) separates serialization, generated definitions, connections and coroutine/reactive adapters. Credible non-Python option; select and measure a concrete Linux target rather than treating JVM and native deployment as equivalent. |
| Java / dronefleet | [Project README](https://github.com/dronefleet/mavlink) exposes low-level CRC/signing but explicitly reports inactive maintenance. Protocol support alone does not settle long-term support or bounded runtime behavior. |
| Clojure, Lua, Ada, Dart | The MAVLink catalog identifies these generator families too. Clojure is listed with signing; Lua has a stated zero-trimming limitation and Dart lacks signing there. The installed generator dispatch also contains an Ada v2 path despite the catalog's v1-only row: this discrepancy prevents dismissing Ada solely from the table. A source/build check would be needed to qualify it. |
| Python / pymavlink | [Upstream SDK](https://github.com/ArduPilot/pymavlink) provides generated dialects and direct decode. Current code has explicit packet/state bounds and an optional native CRC dependency. GC/interpreter scheduling, allocation, full-dialect import and LGPL/native dependency closure require measurement; existing deployment is not a reason to retain it. |

## Executable experiment and limits

Run with the pinned pymavlink 2.4.50 SDK installed and a trusted local C compiler:

```sh
PYTHONPATH=integrations/edge python scripts/robotics_wire_audit_v2.py --out build/wire-audit-fresh
```

The script refuses an existing output directory. It extracts the two messages
from the installed, hash-recorded common XML, uses upstream mavgen C generation,
and compiles an original receive-only audit driver. Generated SDK headers remain
in ignored build output and are not redistributed by this patch. Compiler stages
are limited to 30 seconds, each experiment to 5 seconds; 512 fixed probes per
implementation, no download, Docker, simulator or vehicle connection.

The 17 fixed cases cover both payloads, zero trimming, NaN/infinity, truncation,
CRC corruption, size, magic, flag, sender and message-ID rejection. Accepted
message ID, boot time and six decoded values match, as well as rejection. A
second C build uses AddressSanitizer and UndefinedBehaviorSanitizer on the same
bounded corpus. Tests ensure a candidate admission/value disagreement is rejected
and old evidence cannot be overwritten. This is not a lifecycle parity suite.

Exact [results](../verification/robotics-wire-audit-v2-results.json) retain both
runs: first Python p95 130281 ns / maximum 59938459 ns; second p95 114877 ns /
maximum 524311 ns. C p95 was 336 ns and 334 ns respectively. Both implementations
accepted 92 of 512 mixed probes. C is faster in this limited experiment; **no
general speedup or winner is inferred**. Python includes result/provenance object
work while the C prototype omits temporal state, replay and provenance objects;
Python construction is outside timing, C stack initialization inside. Neither
cold-start nor RSS was measured. Shared-host scheduling may affect outliers;
the initial 59.9 ms observation remains evidence, not an excused/deleted result.

Decision: **PENDING, not KEEP**. These measurements do not prove Python optimal,
nor establish that the smaller C parser is a safe complete replacement. Next at
this same cursor: extend parity to state/expiry and compare a memory-safe native
or managed alternative, including cold-start and memory. Record KEEP/MIGRATE only
after that comparison; implement any winning migration before advancing. No
technology audit completion file is warranted.

Focused verification: the three audit-harness tests initially failed because
the executable comparison was absent. Final audit plus datagram regression run:
21 PASS. Ruff lint/format and Bandit pass; narrow subprocess and XML suppressions
are limited to fixed local commands and trusted installed SDK input. The generated
C comparison compiles with `-Wall -Wextra -Werror`; normal and sanitized admission
parity pass. No full repository suite, full fuzz or hardware qualification ran.

## Managed lifecycle comparison — 2026-10-10 continuation

The next executable comparison is an original JavaScript strict subset in
`tests/mavlink/audit_v2/managed.mjs`, with a receiver state machine and a fixed
CRC/message layout. It uses bounded Buffer reads and BigInt clock arithmetic;
it has no socket or transmit API. This measures a managed-language alternative,
not the node-mavlink/NextGen SDKs, their full dialects or their maintenance cost.
No external npm code, install scripts or new packages are used. JavaScript is
selected for this experiment because the primary MAVLink catalog establishes a
credible protocol ecosystem and its different runtime permits direct resource
comparison; availability of Node alone does not justify a production choice.

```sh
PYTHONPATH=integrations/edge python scripts/robotics_lifecycle_audit_v2.py --out build/lifecycle-audit-fresh
```

The final corpus has 16 cases/48 transitions. It checks independent sample expiry,
the exact 100 ms boundary, clock rollback/invalid types, timestamps beyond 2^53,
boot reset/wrap, sequence wrap/half-range rejection, malformed packet recovery,
nonfinite values, signed-flag rejection and irreversible close. Every returned
state, reason, sample value, unit/frame and provenance field is compared against
the production Python adapter; four negative cases also have independent expected
reasons. Two new tests initially failed for the missing comparison. The final
managed and wire audit tests pass (6 methods), as do Ruff, Bandit and Node syntax
checking. Narrow subprocess suppression covers fixed local audit commands only.
An additional RED-to-GREEN check requires boolean authority fields to retain
their JSON type: Python's ordinary equality would consider `False` equal to `0`.
The comparator now rejects that mismatch while accepting equivalent JSON numeric
representations such as `1` and `1.0`.

[All measurement sets](../verification/robotics-lifecycle-audit-v2-results.json)
are retained, including a final run with type-aware parity. In the second run's
expanded corpus, fresh Python processes reported peak RSS
28920 KiB and whole-process elapsed 0.915–1.412 s; Node 22.23.2 reported
46192–46456 KiB and 0.379–0.689 s. Python uses less resident memory in this
experiment; JavaScript finishes sooner. These numbers include startup, all cases
and JSON output, not just initialization or packet decode. Three repetitions run
sequentially, Python first in each pair; filesystem caches may be warm and the
shared host scheduler is uncontrolled. They are not throughput or real-time
qualification. The Python reference also loads pymavlink and the corpus encoder;
the JavaScript process uses an original minimal decoder. Do not generalize this
comparison to equally trimmed implementations or signed workers.
The final type-aware run also retains a reversed timing pair: JavaScript took
1.919 s versus Python 1.904 s. Neither runtime has a demonstrated worst-case
startup bound, and these samples must not be reduced to an unconditional speed
ranking.

RSS sources are the documented Linux `resource.getrusage` and Node
[`process.resourceUsage().maxRSS`](https://nodejs.org/docs/latest-v22.x/api/process.html#processresourceusage)
interfaces. Clock transport uses decimal strings so JSON cannot silently round
nanoseconds above JavaScript's safe Number range.

The focused robotics workflow now runs both experiments and retains result JSON,
including failed-state receipts when an experiment reaches output initialization.
Workflow presence is not hosted execution evidence. Decision remains **PENDING**:
the managed comparison exposes a resource tradeoff, while the earlier C comparison
omits temporal/replay state and does not settle memory safety. Next compare a
memory-safe native candidate at this same cursor before KEEP/MIGRATE. A larger
runtime is not justified merely by a shorter synthetic run, and current Python
is not retained merely because it is deployed. No forward feature work or audit
completion marker is authorized by these intermediate results.

## Native lifecycle experiment — preparation checkpoint

Execution was pending when this section was written. The later
[hosted evidence review](../verification/robotics-native-hosted-review-v3.json)
confirms checked/optimized prototype execution at `52509c7`; local missing-compiler
failures below remain valid historical evidence. Neither establishes current-head
qualification or a production runtime decision.

Rust is the next candidate because native bounded storage and language-enforced
memory safety address the allocation/safety tradeoff left open by the C and
JavaScript experiments. The [MAVLink Rust project](https://github.com/mavlink/rust-mavlink)
provides a maintained domain ecosystem, including separately selectable transport
and signing features. This motivates evaluation, not adoption. The experiment is
an original two-message implementation, **not a qualification of rust-mavlink**.
It neither downloads nor incorporates that SDK.

`tests/mavlink/audit_v2/native.rs` uses two fixed sample slots, safe checked slices,
explicit little-endian conversion, finite-float admission, sequence/clock latches
and the same provenance fields. `#![forbid(unsafe_code)]` excludes unsafe Rust in
this crate. Rust's documented
[`f32::from_le_bytes`](https://doc.rust-lang.org/std/primitive.f32.html#method.from_le_bytes)
and conversion to f64 preserve the decoded wire value before JSON output. The
prototype has no network or transmit API. Its Linux RSS measurement reads only
`/proc/self/status`, outside the receiver implementation.

```sh
PYTHONPATH=integrations/edge python scripts/robotics_native_audit_v2.py --out build/native-audit-fresh
```

The harness combines the existing lifecycle and wire corpora: 33 cases and 65
transitions, including fractional binary32 values and one-byte zero-trimmed
payloads. Generated Rust constants contain validated inputs only, never expected
results. The fixture generator rejects source-injection strings, invalid
operations, excessive sizes and integers beyond its explicitly limited u128
clock domain. Invalid boolean clock fixtures remain invalid rather than becoming
numeric timestamps. This finite clock domain is an experiment limitation, not a
change to the production Python contract.

The hosted job uses its existing compiler, records its verbose version and binary
hashes, and performs checked and optimized builds with overflow checks and
warnings-as-errors. Compiler execution is bounded to 30 seconds and each candidate
process to 10 seconds. Both profiles must pass complete typed state/value/
provenance parity; the optimized profile has three fresh-process repetitions.
Failed compiler logs, candidate stdout/stderr, expected outputs and partial
measurement receipts are retained. Existing output directories cannot be reused.
The [hosted runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md)
is discovery evidence only: an absent or failing compiler fails this job, never
silently skips it or installs an unreviewed toolchain.

**Local native execution has not occurred.** This Linux lane has no Rust compiler;
three attempted runs failed before compilation. The
[negative receipts](../verification/robotics-native-audit-v2-results.json) retain
that fact and source hashes. Five native-harness tests pass alongside six prior
audit methods; the first three native-harness methods were RED before the harness
existed. Ruff lint/format, Bandit and workflow YAML parsing pass. An initial Ruff
thread-spawn failure and YAML process-spawn failure on the shared host are retained
as environment failures; a bounded retry succeeded. Lint also found two omitted
explicit subprocess `check` flags and an import-order issue, which were fixed.
These results validate the local Python harness and prior experiments, **not Rust
syntax, compilation, parity or performance**.

Even after execution, startup results will need careful interpretation: native
inputs are compiled constants while Python reads JSON and imports the whole SDK
and corpus encoder. Runtime calls use `black_box` to impede folding input decode
away. RSS uses Linux VmHWM for Rust versus getrusage for Python; neither is an
allocation count. No signing/replay, UDP, installed packaging, full integer-domain
parity, real-time bound or physical qualification is included. Source evidence
and preliminary code do not establish a production winner. The audit stays at
component 1, decision **PENDING**, until actual native evidence is reviewed and
any winning migration is implemented. No completion marker is written.
