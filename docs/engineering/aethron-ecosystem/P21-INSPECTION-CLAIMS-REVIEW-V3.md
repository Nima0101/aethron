# C08 offline inspection qualification review — V3, partial

Decision for this pass: **CLARIFY disclosure, output and file-trust limits.**
Reviewed `recording_io`, cloud inspection and intensity inspection. The production
change is an intensity CLI docstring; executable behavior is unchanged. Historical
uncommitted cloud/I/O files are preserved. This partial claims review is not a
runtime KEEP/MIGRATE decision, a new capability, or completion of the full V3
reassessment. The full audit cursor remains C01.

Intensity reports contain complete validated source headers in addition to the
selected counts. Cloud reports likewise retain headers, sample counts and selected
raw coordinates/velocity. Source aliases, acquisition times, coordinate frames,
layouts and digests may disclose or link recording metadata. Omitting paths,
classes, identities and unselected sample values does not make either report
anonymous. Applications own access, disclosure and retention policy. A small
selection is not a privacy guarantee. Raw counts are not calibrated temperature;
raw coordinates and velocity are declarations, not measured accuracy evidence.

The new in-process synthetic CLI control confirms that a successful intensity
report includes the original complete header, selected zero count and non-live
status without the private temporary path. Appending malformed trailing input
after a valid frame produces exit 2, empty stdout and the fixed error. This
verifies existing behavior; no failing production regression is asserted.
Buffering the report until input validation succeeds does not make writing stdout
transactional: a failing destination can receive a prefix before an I/O error.
No output-destination failure guarantee was tested or added.

The regular-file helper checks the final path component and the opened descriptor.
It does not authenticate parent directories, snapshot a concurrently modified
file, enforce access policy or establish a filesystem sandbox. Parent directories
must remain trusted. A recording digest checks the consumed byte stream against
a supplied pin; it does not establish file ownership or immutable storage.
The intensity recording pin is optional, while cloud inspection requires it.
Calibration and recording pins cover different artifacts and must not be confused.

The 30-second replay limit concerns declared acquisition-time span, not wall-clock
execution. The input-byte, frame and selection caps do not certify total process
RSS, scheduler latency or completion time on a physical target. Reports remain
recorded-only; cloud inspection explicitly returns UNKNOWN and no registration.
Neither report establishes live support, free space, a tracked object or authority
to actuate. No timing or resource benchmark was run in this review.

See [source-bound review evidence](evidence/phase2/inspection-claims-review-v3.json).
Source hashes identify reviewed bytes, not trusted execution. Earlier T10 latency
and signed radar startup failures remain unresolved. Hardware, legal and
certification gates remain external. Insufficient information for tactical deployment.
