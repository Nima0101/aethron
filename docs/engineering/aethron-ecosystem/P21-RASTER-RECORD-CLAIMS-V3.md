# C06 result-record boundaries — V3, partial

Decision: **CLARIFY constructor, mutability and serialization claims.** A frozen
result dataclass is not a validation or evidence-admission boundary. Direct
construction accepts dimensions, modality and buffers without validation; field
annotations do not enforce types. Normal field reassignment raises, but a
caller-supplied bytearray can still be modified through its original reference.
This does not mean the remapping functions return mutable buffers: they explicitly
construct bytes. Their implementation and admission behavior are unchanged.

The `version` and `live_evidence` properties are not dataclass fields and are
omitted by `dataclasses.asdict`. A generic conversion therefore neither preserves
a complete versioned evidence envelope nor authorizes live use. Such conversion
also retains the data and validity buffers, as the earlier privacy control shows.
Do not infer successful validation, source provenance or permission from a class
name, frozen declaration or absence of a live-evidence field.

Two added methods exercise direct records for mono8 and mono16. They confirm
field reassignment rejection, retained mutable references, unchecked constructor
values and the exact serialized field set. Both passed before the docstring
change. No RED production defect is claimed: these are negative claim controls.
The three-method claims class passes afterward. Ruff/format pass; Bandit reports
zero findings for the production module and test file. Removing docstrings from
the production AST yields an exact match with the parent revision. No operational
algorithm, admission control, threshold, schema or dependency is changed.

Python's official [dataclasses documentation](https://docs.python.org/3.13/library/dataclasses.html)
(inspected 2026-10-10) describes type-annotation handling, emulated freezing and
field-based conversion. This pass establishes actual representation limits,
not a language comparison or runtime KEEP/MIGRATE decision. No new component,
benchmark, device measurement or technology-completion claim is introduced.
Full V3 technology review remains incomplete at C01. Historical evidence remains
unchanged. See [source-bound checks](evidence/phase2/raster-record-claims-v3.json).
