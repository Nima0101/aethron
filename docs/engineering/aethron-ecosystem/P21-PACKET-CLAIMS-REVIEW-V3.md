# C01 packet claims review — V3, partial

Decision for this pass: **CLARIFY qualification and ownership claims**. The
reviewed implementation is `sensors/packets.py` at local commit
`c084b37692ed446824b51e0d9e850b05f8e2eac6`. No production code, decoding behavior,
performance optimization, transport or actuation capability changes in this pass.
This is not completion of the fresh C01 technology review or the P2.1 audit.

The historical V2 note incorrectly named an `Image` result; the implementation
returns `Raster`. It also left the meaning of immutable results and the 8 MiB
bound insufficiently precise. The note now identifies frozen attribute behavior,
mutable nested containers and the distinction between payload size and process
memory. Its old cursor table is explicitly a historical checkpoint.

## Current evidence and limits

- Packet decoding accepts caller-supplied layout metadata and bytes. It has no
  acquisition clock, calibration trust, identity authority or live-evidence
  qualification. A caller's field name or unit declaration does not independently
  establish physical measurement provenance.
- `layout_digest` hashes layout metadata. It does not cover sample bytes, sign
  anything, authenticate a source, grant authority or prove physical calibration.
  It cannot establish MLS, ZTA, cryptographic compliance or end-to-end integrity.
- Closed schemas reject unknown identity metadata fields. That is a schema
  restriction, not proof that arbitrary imagery contains no identifying content.
  No privacy or surveillance qualification follows from the three checks below.
- Invalid depth returns `None`; it is not absence or free space. Nonfinite cloud
  samples are counted and keep an invalid ordinal in `sample_points`.
- 4096 points and 8 MiB payload are input bounds. Python objects, caller buffers,
  interpreter and libraries use additional memory. No total RAM bound, worst-case
  execution time, availability target or physical sensing range is established.
- Frozen dataclasses/Pydantic models prevent ordinary attribute reassignment;
  they are not protection against hostile in-process code. A frozen model does
  not recursively freeze `CloudLayout.fields`. Directly constructed result
  objects must not be mistaken for authenticated decoder outputs.

Three existing safety-focused methods were rerun: image malformed/identity
metadata rejection, cloud malformed/identity metadata rejection, and depth-scale/
unknown-depth semantics. All passed. No new test was added solely to mirror this
documentation correction. No broad suite, new benchmark or hardware check ran.

## Technology evidence status

The V2 comparison executed `struct.Struct`, NumPy strided views and a Node Buffer
worker, with source-only JVM ByteBuffer and Kaitai comparisons. That evidence
remains available, including mixed-width results favorable to alternatives and
excluded worker pipe-I/O CPU. It does not establish a fresh V3 runtime winner.

Current official references confirm what the primitives promise:
[struct](https://docs.python.org/3/library/struct.html#struct.Struct) documents
binary representation handling;
[Node Buffer](https://nodejs.org/api/buffer.html#bufreaddoubleleoffset) documents
endian-aware reads. Neither supplies physical qualification or application
security policy. The executed Node process is one bridge design, not proof that
all non-Python implementations need IPC. No inference about unmeasured native
bindings or Java/Julia performance is justified.

[Python frozen dataclasses](https://docs.python.org/3/library/dataclasses.html#frozen-instances)
and [Pydantic faux immutability](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability)
support the corrected ownership wording. Documentation retrieval on 2026-10-10
is not a new package version pin or a security clearance.

C01's full fresh review remains open. Further work here is limited to civilian,
read-only validation and qualification evidence; this note does not qualify any
targeting, engagement, unauthorized-access or autonomous-actuation integration.
Historical T10 latency failure, signed radar startup timeout and external
hardware/legal/certification gates remain unaltered. Insufficient information
for tactical deployment.
