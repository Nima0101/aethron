# P2.1 boot diagnostic claim review — V3, partial

Decision: **CLARIFY recent activity and historical flag semantics.** This pass
reviews the raw sensor observer within the offline appliance, not the peer-owned
service manager, capture clocks or ROS/telemetry lifecycle. Full technology
reassessment remains incomplete at C01. No KEEP/MIGRATE decision, runtime
optimization, hardware qualification or new boot/soak result is recorded.

The legacy `processing_at_end` name can be misread as current health. The actual
predicate accepts last activity at any age from 0 through 2000 ms. A later fault,
stalled counter or rejected sample does not invalidate it. Recovery and update
flags are historical latches. They can remain true when recent activity has
expired. This does not prove uninterrupted operation, five-nines availability,
failover or the health of the latest observation.

Two new test methods demonstrate these limits before any documentation change:
fault/stall/invalid transitions preserve recent activity through the inclusive
endpoint but not beyond it; recovery/update flags survive activity expiry.
They pass against the original implementation. There is no claimed RED software
regression for this clarification. Existing observation and fault counters remain
visible. Runtime AST comparison excluding the module docstring is unchanged.

The observer assumes trusted status mappings and monotonic integer milliseconds
in a common clock domain. It does not authenticate input or independently
validate the host clock. At most four profile rows are retained; cumulative
counters grow with the run, so the old unqualified “bounded” module description
is narrowed. No hard deadline or memory ceiling is inferred.

Historical raw-boot evidence, including the unexplained source-run missing
processing assertion and the absence of a current raw-profile boot soak, remains
unchanged. Focused tests load only the observer and synthetic dictionaries. They
do not launch a VM, signed image, worker, DDS endpoint or device. Source hashes
identify reviewed bytes, not authenticated execution. See
[review checks](evidence/phase2/boot-diagnostic-claims-v3.json).
