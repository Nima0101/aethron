# Passive SDK startup and CRC fallback characterization

This is P3.1 diagnostic software evidence, not target-platform timing qualification.
The reviewed receiver is unchanged from `364d702`. The probe uses the portable
installed wheels built from `063c8d7`; its regression test compares the installed
receiver's file hash with the current checkout. Both contain the same receiver.

The [probe](../../tests/mavlink/sdk_startup_probe_v3.py) runs only on Linux under
an isolated interpreter with the core/edge wheels and the pinned optional SDK
installed. Each invocation uses a fresh process. Reproduce the two modes with:

```sh
.venv/bin/python -I tests/mavlink/sdk_startup_probe_v3.py installed
.venv/bin/python -I tests/mavlink/sdk_startup_probe_v3.py blocked
PYTHONPATH=integrations/edge:tests/mavlink .venv/bin/python -m unittest test_sdk_startup_v3 test_telemetry
```

`blocked` installs a process-local import hook that raises ImportError for
`fastcrc`. It neither uninstalls dependencies nor edits SDK files. The generated
pymavlink 2.4.50 common dialect catches that exception and selects its Python CRC
implementation. This is a characterization of the pinned installed source; the
[upstream CRC implementation](https://github.com/ArduPilot/pymavlink/blob/master/generator/mavcrc.py)
also documents optional acceleration. Installed package version alone does not
identify the selected backend. The generated common module and selected loaded
package files, including the native extension when present, are hashed after
the measurements. These are local file identities, not signed attestations or
proof against concurrent file replacement or in-memory modification.

The measurement intervals cover adapter import, first construction (including
lazy SDK import and version checking), and second construction (including a
small cleanup-ownership list update). `sys`, `time` and `resource` are already
imported before measurement. Process launch, interpreter initialization, later
packet checks, output serialization and hashing are excluded. Peak RSS is sampled
after the second construction, before packet checks and metadata hashing, using
Linux `getrusage` units. It is process high-water RSS, not retained-object size,
per-constructor allocation, a measured upper bound, or a cross-language metric.
Python's [monotonic clock documentation](https://docs.python.org/3/library/time.html#time.monotonic_ns)
supports integer elapsed observations, not scheduler or startup guarantees.

Both modes accept the same two fixed synthetic packets, report unverified
observations, reject a CRC-corrupt packet with empty UNKNOWN/`invalid_packet`,
remain perception-ineligible and support explicit close. Receipt schema 2 adds
`accepted_status`, captured before corruption: both samples explicitly retain
`external_unverified`, `authenticated=false`, and null capture time, link ID and
signature timestamp. The status has `perception_eligible=false`. These fields
are read from the receiver's returned objects, rather than inferred from message
names or from the later empty UNKNOWN status. The top-level `perception_eligible`
field continues to describe only the corrupt-packet status. The normal installed
mode selects `_x25crc_fast`; simulated import failure selects `_x25crc_slow`.
`lxml` is installed as a package dependency but is not loaded by either probe
path. This distinguishes installation dependencies from observed runtime imports;
it does not establish that lxml can be removed from the package closure. There
are no socket operations, live sources, keys, persistence or actuation.

The [historical schema-1 results](robotics-sdk-startup-v3.json), committed at
`fbd4d706ab6190d3634cdc9cf6b8576e15c080fe`, retain three process pairs from that
probe and an earlier six-process run before the explicit Linux guard was
added. The earlier run overlapped focused tests; its 84,424,117 ns second-constructor
observation is retained. The final pairs ran after those tests, but the host
remained shared and filesystem caches uncontrolled. No readings are discarded
and no timing threshold or runtime ranking is inferred. The initial run is
historical evidence, not execution of the final probe bytes. The final probe
bytes were captured before the six runs and checked unchanged afterward. Those
source hashes identify the historical commit, not today's schema-3 probe.

The [schema-2 provenance results](robotics-sdk-provenance-v3.json) retain a fresh
process in each mode, two RED assertions for the missing accepted-status field,
and 14 passing focused tests with zero skips. This closes an evidence gap:
the original probe asserted message names and checked eligibility only after
corruption. It did not directly test the accepted observations' provenance.
No production defect or production-code change is claimed. The new raw receipts
retain incidental timings without a comparison or performance conclusion.

The [schema-3 closure results](robotics-sdk-closure-v3.json) correct a separate
evidence gap. Earlier probes called close only after corrupt input had already
emptied the first receiver, then exported its reason alone. That sequence did
not demonstrate withdrawal of populated slots or refusal of later admission.
The second receiver now accepts both fixed packets, closes, and receives the
same packets again. `closure_status` records its populated precondition and
the actual returned states after close and attempted readmission. Both must be
empty UNKNOWN with reason `closed` and `perception_eligible=false`. The older
`closed_reason` still describes the first receiver after corruption. Historical
schema-1/2 receipts remain unchanged; schema 2 is bound to commit `48de56c`.
This is informational-output lifecycle evidence only: no vehicle shutdown,
remote kill-switch, memory zeroization or erasure of caller-held snapshots is
demonstrated. The new checks run after all timing/RSS samples and do not alter
their intervals. Incidental new timings are retained without ranking runtimes.

The missing probe produced two RED test assertions. The completed probe and
passive receiver tests pass with no Linux skips. The installed-source comparison
prevents an older wheel from silently satisfying these new tests. This is a new
measurement/characterization tool; the RED was not a production decoder defect.

Technology choice for this probe follows the observation boundary: Python must
execute its own import and construction stages to expose backend selection.
An external C/Rust/JavaScript launcher could time a whole process but would not
separate these internal stages without the same interpreter instrumentation.
This rationale does not award Python a production KEEP decision. The full
Python dialect still differs from the original native/managed two-layout
prototypes. Consequently these observations do not settle the runtime decision;
that review remains open. This probe is restricted to non-actuating synthetic
diagnostics and provides no evidence for weapon integration.

The safe-embedded addendum's modular interfaces, source validation and honest
timing evidence apply here. These fixtures establish only the behaviors above.
Physical source authorization, synchronization, target OS/hardware WCET, watchdog
deadlines, proprietary/Link 16 interoperability and customer release acceptance
remain unqualified. No new transport, watchdog, cryptographic compliance or P19
acceptance is implemented by this probe. Insufficient information for tactical
deployment.
