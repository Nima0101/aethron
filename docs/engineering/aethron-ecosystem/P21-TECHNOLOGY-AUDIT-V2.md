# P2.1 retrospective technology audit — policy v2

This audit starts with the earliest raw-packet component and proceeds through the
existing P2.1 implementation. It is incomplete: forward feature expansion is
paused. A prior technology note is not a completed policy-v2 reassessment.

| Cursor | Existing component | Decision |
| --- | --- | --- |
| C01 | Raw sensor packets (`packets.py`) | KEEP Python validation/result boundary; replace scalar-per-field kernel with compiled record decoding |
| C02 | Binary cloud/image replay | Pending |
| C03 | Pinhole geometry | Pending |
| C04 | Rig calibration/registration | Pending |
| C05 | Lens rectification | Pending |
| C06 | Recorded-raster rectification/native-backend consumption | Pending |
| C07 | Calibrated intensity replay binding | Pending |
| C08 | Offline recording I/O and inspection | Pending |
| C09 | Offline sensor appliance | Pending |

Provider/runtime, ROS interfaces, capture/timebase/process isolation and the
native raster producer remain peer-owned. Their published interfaces may be
consumed; this audit does not create competing implementations.

## C01 constraints

Linux, shared 6.3 GiB host, offline/read-only operation, no device SDK or actuator.
The public packet boundary returns immutable Python `Image`, `Point` and `Cloud`
values. Its strict metadata rejects boolean numeric fields, nonfinite metadata,
unknown fields and unsupported layouts. Images are bounded to 1920×1080 and
8 MiB with explicit encoding/scale; ingestion retains immutable input bytes,
without a full-raster transform. Cloud layouts allow at most 4096 samples,
12–128-byte records, both byte orders, unaligned FLOAT32/FLOAT64 XYZ and optional
signed radial velocity, unordered fields and row padding. Nonfinite sample
fields invalidate that ordinal, not the whole packet. Neither output carries
identity, classes, provenance authority or physical qualification.

The comparison must include validation and conversion to that result boundary,
not just a scalar-load microbenchmark. No hard packet latency target is newly
invented. Bounded work, memory, exact semantics and a small offline deployment
surface are decisive; installed tooling and rewrite cost do not establish a win.

## Candidates and primary evidence

- **Compiled `struct.Struct` records:** [Python's documented standard-size,
  explicit-endian buffer operations](https://docs.python.org/3/library/struct.html#struct.Struct)
  can decode each point once while preserving unaligned offsets. Prototype and
  production paths were compared with the retained scalar baseline.
- **Strided NumPy structured arrays:** [the ndarray buffer/dtype/strides
  interface](https://numpy.org/doc/stable/reference/generated/numpy.ndarray.html)
  directly represents padded rows and byte order. The prototype uses a buffer
  view, with no flattening copy; conversion to Python result objects is included.
  NumPy 2.3.5 came from the existing hash-pinned vision lock via official PyPI,
  only in the probe environment. It is not a new packet runtime dependency.
- **Node.js Buffer worker:** [bounds-checked endian-aware floating-point
  reads](https://nodejs.org/api/buffer.html) support the layout without a device
  SDK. An executable persistent binary-pipe worker prebinds readers and returns
  fixed-width records. Python validation and result conversion are included.
  This tests a credible technology outside the component's language.
- **JVM ByteBuffer:** [Java 21 absolute floating-point reads and explicit byte
  order](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html)
  are a viable managed binary-parser substrate. This is a source comparison,
  not a measured JVM result. It would require an additional runtime and bridge
  to return this boundary; no SDK constraint or demonstrated advantage justifies
  that migration here.
- **Kaitai generated parsers:** [calculated byte order and sized substreams](https://doc.kaitai.io/user_guide.html)
  offer a credible declarative parser approach. Dynamic externally validated
  field offsets, application bounds, invalid-sample semantics and conversion to
  the result boundary remain application responsibilities. No fixed device
  wire-format schema is being implemented by this component; source review did
  not establish a material advantage. No generated-parser benchmark is claimed.

## Executable decision

KEEP the Python schema/result boundary and deploy one compiled native record
unpack per point. This changes the existing implementation, rather than merely
endorsing its original technology. No new dependency, child process, FFI or
language runtime is introduced. Sorted validated fields build explicit padding
and standard endian/width codes once per packet; output ordinals and signed zero
remain unchanged. Images continue their no-transform immutable-byte boundary.

Two synthetic 4096-point fixtures include padding, unordered fields and 241
invalid samples each. The second adds big-endian, unaligned mixed widths. All
candidates matched the complete baseline result for 15 rotated samples per case.
Median CPU milliseconds (parent plus measured worker kernel where applicable):

| Implementation | Little-endian float32 | Big-endian mixed widths |
| --- | ---: | ---: |
| Original scalar baseline | 13.326 | 14.843 |
| Production compiled records | 5.982 | 6.194 |
| Strided NumPy plus result conversion | 6.633 | 5.538 |
| Persistent Node plus result conversion | 7.859 | 5.695 |

The mixed-width case favors NumPy and Node; the float32 case favors production.
The measured alternatives therefore do not demonstrate a uniform throughput win.
NumPy increased peak process RSS from 29,312 to 42,752 KiB in a separate import
probe. The Node worker alone used 42,224–42,308 KiB and took 118–262 ms to become
ready on this contended host. Node's combined CPU excludes worker pipe I/O and is
a lower bound. These memory/startup values are observations, not universal costs.
A modest single-fixture speed advantage does not materially outweigh an added
runtime/dependency and memory footprint for this bounded standalone packet API.
If future consumers accept array-native results or measured workloads establish
a different bottleneck, reassess the versioned boundary instead of assuming this
choice applies to all numerical components.

Production CPU fell about 55–58% against the original baseline on these fixtures.
Wall p95 remains noisy (73.8–80.4 ms for production); this is not real-time,
hardware, sensor-accuracy or field qualification. No frozen threshold changed.
The source-only JVM/Kaitai comparisons establish feasibility, not inferiority on
unmeasured performance axes. This is an evidence-backed component decision, not
an exhaustive proof over every implementation technology.

## Regression and retained limitations

A deterministic RED test observed 128 native unpack calls for 32 four-field
samples, exceeding the one-per-sample work budget. Production passes that test.
A second regression covers unaligned mixed-width fields, padding, nonfinite
ordinals and signed zero. The packet/replay/inspection selection passed 29 tests,
including the existing 2000 seeded replay corruptions. An installed wheel passed
all 10 packet tests. Ruff lint/format, Node syntax and production Bandit are
required focused checks; see the accompanying evidence for recorded outcomes.

The [reproducible probe](../../../scripts/probes/sensor_packet_audit/README.md)
and [machine-readable evidence](evidence/phase2/technology-v2-packets.json)
retain earlier experiments rather than replacing unfavorable observations.
The initial system-interpreter attempt lacked Pydantic and did not produce a
measurement. Earlier probes used less favorable conversion paths or omitted
worker CPU accounting; they remain labeled superseded. Shared-host scheduling
precludes a hard latency conclusion. Historic frozen T10 latency and signed
radar startup failures are not cleared by these focused tests. Hardware, legal,
calibration and certification gates remain external.
