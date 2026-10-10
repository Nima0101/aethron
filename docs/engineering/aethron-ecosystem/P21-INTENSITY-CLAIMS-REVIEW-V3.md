# C07 intensity binding qualification review — V3, partial

Decision for this pass: **CLARIFY provenance and lifetime claims; add a repeated
call control.** Existing code correctly describes the calibration pin as an
equality check and keeps results recorded-only. The source-header and repeated
call limits now also appear in the API docstring. Executable behavior, schemas,
thresholds and dependency versions are unchanged. This partial claims review
neither establishes a KEEP/MIGRATE decision nor completes the fresh V3 technology
reassessment. The full audit cursor remains C01.

The calibration digest covers the declared calibration document. The payload
digest covers the original raster bytes, including padding. Neither authenticates
the source alias, physical device, acquisition time, ownership or calibration
accuracy. Trust in an independently supplied pin comes from the caller's process,
not from this function. Python documents ordinary
[hash digests](https://docs.python.org/3.13/library/hashlib.html) separately from
[keyed message authentication](https://docs.python.org/3.13/library/hmac.html);
these official references were inspected 2026-10-10. No authentication mechanism
is added or claimed here.

`RecordedIntensity.source_header` is retained raw-input metadata. Its dimensions
and payload digest must not be presented as describing the remapped raster. The
new synthetic control uses a three-pixel padded input and a four-pixel output:
the retained header still has width three and the original byte digest, while
the output has width four and different bytes. No output attestation is produced.
The separate validity mask remains necessary; it is not sensor-quality evidence.

The single-frame function has no trusted-current-time argument or replay history.
The control invokes it twice with the same frame and confirms that sequence,
acquisition time and uncertainty stay unchanged. Both results remain recorded
and non-live. Reader-level continuity checks operate within that reader's stream;
they do not make this standalone call an anti-replay or freshness authority.
Reprocessing archived data is not new evidence.

Full-file equality, when required by the offline inspection caller, is a separate
recording-pin boundary; calibration and per-payload digests alone do not identify
a complete file. This review does not change that interface or the file reader.
It does not introduce a clock conversion, new provenance field, device adapter,
tracking state or operational capability.

See [source-bound evidence](evidence/phase2/intensity-claims-review-v3.json).
The test passes against existing behavior before the docstring clarification;
no production defect or security remediation is asserted. No benchmark or physical
qualification was performed. Hash bindings identify bytes, not authenticated
execution. Historical T10 latency and signed radar startup failures remain.
Hardware, legal and certification gates remain external. Insufficient
information for tactical deployment.
