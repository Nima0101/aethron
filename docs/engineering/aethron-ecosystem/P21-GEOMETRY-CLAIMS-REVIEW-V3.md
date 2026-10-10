# C03 geometry qualification review — V3, partial

Decision for this pass: **CLARIFY historical status and qualification limits.**
No production, contract, test or benchmark implementation changes. This is an
independent review of claims, not a completed technology reassessment. The full
V3 cursor remains at C01; prior KEEP decisions do not satisfy the fresh review.

The earlier C03 note described its C04–C09 audit status in the present tense.
It now identifies that status and its KEEP decision as a historical V2
checkpoint. Historical source hashes for the geometry implementation, numeric
tests and comparison script were checked against current bytes. Matching hashes
bind those bytes only; they do not authenticate the origin or execution of a
benchmark report.

The numerical envelope is distinct from physical qualification. Deprojection
bounds supplied axial depth; the separate range method bounds Euclidean norm.
Projection checks positive Z and image containment but does not itself apply
the 500 m range limit. None of these methods measures physical sensor reach,
estimates calibration accuracy or verifies that coordinates are observations.
Synthetic round trips and finite-number checks cannot establish those claims.
There is no new range authorization or changed threshold in this correction.

The historical comparison covers a scalar interface on one shared host. The
retained report provides CPU/wall medians and traced peaks, not the individual
15 timing samples. Its aggregate values cannot reconstruct dispersion, jitter,
tail latency or a worst-case execution bound. Traced allocation measurements do
not establish total process RSS, all native allocations or a deployment memory
ceiling. The host memory observation is not a product requirement or guarantee.
No timing measurements were rerun or silently replaced in this pass.

Primary references inspected 2026-10-10:
[Python 3.13 math](https://docs.python.org/3.13/library/math.html#math.hypot)
describes a numerical Euclidean norm;
[Python 3.13 tracemalloc](https://docs.python.org/3.13/library/tracemalloc.html)
describes traced allocations. Neither is physical calibration evidence.
The historical NumPy challenger and source-only Julia StaticArrays, Eigen and
OpenCV comparisons remain evidence inputs. This pass establishes no new runtime
ranking, native migration decision or performance optimization.

Two existing negative test methods were run: Euclidean range rejection and
nonfinite/overflow rejection. They verify the recorded software checks only.
No new failing production case or corrected numerical algorithm is claimed.
The accompanying [review evidence](evidence/phase2/geometry-claims-review-v3.json)
records the checked source bindings and review scope.

Hardware, legal and certification gates remain external. Historical T10 latency
and signed radar startup failures remain retained. No hard-real-time, five-nines,
MLS, cryptographic-compliance or targeting/actuation qualification follows from
these tests. Insufficient information for tactical deployment.
