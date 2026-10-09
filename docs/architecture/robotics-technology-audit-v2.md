# Robotics implementation reassessment v2 — in progress

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
