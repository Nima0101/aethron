# C04 calibration qualification review — V3, partial

Decision for this pass: **CLARIFY provenance and lifecycle claims; correct test
wording and strengthen retained-result coverage.** Production registration code,
public schemas, thresholds and digest encoding are unchanged. This independent
claims review is not a completed V3 technology reassessment. The full audit
cursor remains C01; the V2 KEEP decision is historical evidence only.

The test previously named `test_rebind_invalidates_previous_geometry_and_requires_new_clock_domain`
created its replacement with the same clock domain. It also checked future
calls after close, not erasure of a previously returned result. The test is now
named for its actual behavior and checks retained digest/expiry/scene-break
metadata and `live_evidence=False` after close. It explicitly observes that the
replacement uses the same clock domain and starts a scene break. These are
existing semantics, not a newly fixed runtime defect or a new clock authority.

A binding trusts caller-supplied time values and a clock-domain label. It does
not read a trusted clock itself, establish synchronization or authenticate the
clock source. Its checks apply when called; there is no background revocation
of result objects. A retained result does not become fresh merely because a
new binding exists. Downstream consumers remain responsible for current-time,
expiry, scene continuity and source validity checks.

`RigCalibration.digest` hashes serialized calibration fields. It does not cover
individual measurement payloads, authenticate the declarant or certify a mount,
sensor, calibration procedure or physical error bound. Reconstructing the model
checks declared structure and numerical constraints. It does not prove that
those declarations match reality. `live_evidence` remains false for every
returned registration result. No identity or observation history is introduced.

The read-only public calibration property is an API ownership rule, not process
isolation. The binding remains thread-confined and has mutable lifecycle state.
Neither frozen models nor Python private naming creates a security boundary
against arbitrary code in the same process. The current upstream
[Pydantic model documentation](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability)
distinguishes model validation and faux immutability; Python's
[hashlib documentation](https://docs.python.org/3.13/library/hashlib.html)
describes digests. These sources were inspected 2026-10-10 and support this
terminology, not hardware or cryptographic-compliance claims.

The earlier NumPy experiment and source-only SciPy, Julia IntervalArithmetic
and Boost.Interval comparisons remain historical evidence. No new runtime
ranking, native implementation, numerical optimization or performance run is
performed in this pass. Retained timing summaries and synthetic tests cannot
establish deterministic execution, measured calibration accuracy or uptime.

Four focused registration test methods check retained-result semantics,
non-live/identity metadata rejection, malformed calibration loading and closure
after a clock rewind. The updated case passed against unchanged production;
there is no claimed RED-to-GREEN production fix. Source hashes and precise scope
are retained in [review evidence](evidence/phase2/registration-claims-review-v3.json).
Historical T10 latency and signed radar startup failures remain uncleared.
Physical, legal and certification gates remain external. Insufficient information
for tactical deployment.
