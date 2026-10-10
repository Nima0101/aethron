# C07 result-record boundaries — V3, partial

Decision: **CLARIFY construction and conversion claims.** `RecordedIntensity`
is a storage wrapper. Direct construction does not execute calibration or payload
binding checks; its version, recorded and non-live properties exist even when
all three constructor arguments are None. These labels cannot attest that the
binding function ran. The function's existing checks are unchanged.

Representation suppression omits the header, calibration and raster from repr,
not from dataclass conversion. `asdict` returns those three fields without the
version, source_evidence or live_evidence properties. It is not a versioned wire
evidence envelope, an authorization decision or a redaction mechanism. Frozen
fields also do not freeze mutable objects a caller supplies directly. This does
not characterize outputs of the validating binding function as dictionaries:
the new controls deliberately use unchecked direct records to test that boundary.

Two controls use None and small synthetic dictionaries. The dictionary conversion
retains fixture contents while its copy stays separate from a later caller
mutation; the original record still references the caller's dictionary. No lens
kernel, frame reader, pin validator or physical sensor executes in these tests.
Both methods pass before and after the docstring clarification. No failing
production defect or security remediation is claimed. Ruff/format and two-file
Bandit pass with zero findings; production AST excluding docstrings is unchanged.

Python's official [dataclasses documentation](https://docs.python.org/3.13/library/dataclasses.html)
(inspected 2026-10-10) describes field conversion and the limits of freezing.
This is a claim-verification correction, not a new runtime or technology ranking.
No schema, dependency, threshold, executable sensor behavior or historical
report changes. Full V3 technology reassessment remains incomplete at C01;
no KEEP/MIGRATE decision, benchmark or completion marker is introduced.

See [source-bound checks](evidence/phase2/intensity-record-claims-v3.json).
