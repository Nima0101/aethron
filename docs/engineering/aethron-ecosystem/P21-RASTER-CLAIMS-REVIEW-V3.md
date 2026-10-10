# C06 recorded raster qualification review — V3, partial

Decision for this pass: **CLARIFY sampling and privacy claims; verify existing
serialization behavior.** The production change is a docstring only. Arithmetic,
thresholds, layouts, return types and admission behavior are unchanged. This
limited review does not select a runtime, complete the retrospective technology
reassessment or advance the full audit cursor past C01.

The output validity byte records whether the declared geometric mapping sampled
an allowed source pixel. It does not certify sensor health, exposure, scene
visibility, physical calibration or evidential support. Zero can be a sampled
count or storage for an invalid ray; the separate mask distinguishes these
cases. Neither case establishes an empty scene. Unsigned intensity counts alone
are not calibrated temperature, distance or confidence measurements.

`repr=False` suppresses the two buffers in the generated representation. It is
not redaction, encryption or an authorization boundary. Generic
[`dataclasses.asdict`](https://docs.python.org/3.13/library/dataclasses.html#dataclasses.asdict)
includes their contents (official reference inspected 2026-10-10). Remapping
preserves image information and provides no guarantee of anonymity. Applications
must apply their disclosure and retention rules before storing or exposing the
result. Frozen dataclasses likewise do not authenticate the supplied input or
its origin.

The new two-pixel synthetic control exercises both mono8 and mono16. Identical
stored zeros have one sampled and one invalid position; access returns zero and
None respectively. Both results remain non-live. Their representations omit
buffers while dataclass conversion retains both. This verifies existing behavior;
no failing production regression or privacy fix is claimed.

The 327,680-output-pixel cap bounds this output shape, not whole-process memory,
retained caller objects, execution deadlines or scheduler jitter. Temporary and
returned buffers coexist during construction. No physical target, sensor quality,
real-time performance or complete deployment qualification was measured here.
No benchmark, new runtime ranking or operational enhancement is included.

See [source-bound review evidence](evidence/phase2/raster-claims-review-v3.json).
Source hashes identify reviewed bytes, not trusted execution or authorship.
Historical T10 latency and signed radar startup failures remain retained.
Hardware, legal and certification gates remain external. Insufficient
information for tactical deployment.
