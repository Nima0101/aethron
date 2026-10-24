# Reproduce the supplied-clock negative evidence

The [recorded result](robotics-clock-exception-claims-v3.json) describes two
synthetic cases but previously supplied no executable reproduction. This command
reproduces those observations against the passive implementation recorded at
commit `47480100aec56673749863463340333433bfa0b2`. Run from the repository root
with the existing optional telemetry environment (`pymavlink==2.4.50`). It opens
no socket and sends no telemetry. It does not modify the clock or production code.

The snippet directly invokes the Python callable boundary under examination.
Using a different runtime would introduce a bridge and would no longer reproduce
the same exception propagation path. This is a reproduction of existing evidence,
not a production language selection or a new transport implementation. Python's
[exception and cleanup semantics](https://docs.python.org/3/tutorial/errors.html)
explain the selected `RuntimeError` handler and unconditional `finally` cleanup.

```sh
PYTHONPATH=integrations/edge .venv/bin/python - <<'PY'
import json

from aethron_edge.telemetry.mavlink import PassiveTelemetry
from pymavlink.dialects.v20 import common


class Clock:
    failing = False

    def __call__(self):
        if self.failing:
            raise RuntimeError("synthetic_clock_failure")
        return 1_000_000_000


results = []
for operation in ("snapshot", "ingest"):
    clock = Clock()
    source = PassiveTelemetry(1, 1, clock=clock)
    try:
        encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
        packet = common.MAVLink_attitude_message(10, 1, 2, 3, 4, 5, 6).pack(encoder)
        source.ingest(packet)
        before = source.snapshot()
        clock.failing = True
        propagated = False
        try:
            if operation == "snapshot":
                source.snapshot()
            else:
                source.ingest(b"")
        except RuntimeError:
            propagated = True
        clock.failing = False
        after = source.snapshot()
        source.close()
        closed = source.snapshot()
        results.append({
            "operation": operation,
            "clock_exception_propagated": propagated,
            "before_state": before.state,
            "after_recovery_state": after.state,
            "retained_sample_count": len(after.samples),
            "after_close_state": closed.state,
            "after_close_reason": closed.reason,
            "perception_eligible": after.perception_eligible,
        })
    finally:
        source.close()

print(json.dumps({
    "scope": "synthetic in-process clock fault; no transport",
    "results": results,
    "general_clock_exception_latch_established": False,
}, indent=2))
# This observation-only probe never certifies general clock-fault handling.
raise SystemExit(1)
PY
```

Expected historical observation: both exceptions propagate, both recovered
snapshots retain one `OBSERVED_UNVERIFIED` sample, and explicit close yields
`UNKNOWN` / `closed`. Perception eligibility stays false. Compare the emitted JSON
with the `probe` member of the recorded result; exit code 1 alone does not prove
reproduction, since an import or execution failure can also exit nonzero.
Changed output requires review rather than changing the historical receipt.

The final false field and exit code 1 are deliberately unconditional: this small
characterization cannot establish general latching even if a later implementation
changes the two observations. It is not a passing qualification test, an expected
failure exemption in CI, or a fix. Hardware, scheduling, other exception classes,
and other adapters remain outside this experiment.
