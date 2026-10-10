# P16 consumed sensor encoding review v3

Reviewed 2026-10-10 against `ffd019cf746adac2a069eeb5fd23316cbd0b5ad8`.
The producer remains peer-owned and unchanged. Its three consumed source files match
cached `origin/main` at `a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46`.
This is a consumer conformance correction, not physical qualification or a new adapter.

## Constraint and technology decision

The requirement is to test exact byte binding against the published P2 decoder, offline,
with tiny analytical packets and no device access, actuation or latency target. The
portable fixture must preserve the existing signed base corpus and its producer pins.

KEEP direct Python API tests with language-neutral JSON vectors. The actual decoder
uses Pydantic strict validation; [strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)
has type- and input-dependent behavior, so calling the real producer tests its boundary.
Structural JSON Schema validation cannot establish pixel values or authentication.
[Kaitai Struct](https://kaitai.io/) offers declarative binary formats and generated
parsers in languages including Java and Nim, credible alternatives outside this
consumer's language. A generated parser would test a second implementation, rather
than the published producer; adding one here would duplicate peer ownership without
satisfying this requirement. No runtime speed ranking or hard real-time claim follows
from this decision. These options are compared for this narrow consumer, not as a
fixed candidate list for P18 hardware adapters.

The public ROS [Image definition](https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/msg/Image.msg)
documents byte order, full row length and payload size. It motivates these boundary
cases but does not establish ROS compatibility: the consumed AETHRON JSON is not a
ROS message, and this test has no ROS transport. The ROS documentation site returned
an access-denied challenge; the official source definition was read instead.

## Missing coverage corrected

The earlier corpus covered scale substitution, changed pixels, signed truncation and
zero depth, but did not test equivalent encodings, row padding or trailing bytes.
Two new test methods initially failed because the new corpus was absent; the existing
five methods passed. No production defect was demonstrated.

The separate `sensor-encoding-vectors-v1.json` references the unchanged original
corpus by SHA-256. Four cases reuse its original authentication without resigning:

| Case | Independent decoder result | Original byte authentication |
|---|---|---|
| Big-endian equivalent | zero is unknown; other sample 5.0 m | rejected |
| Byte-order flag changed alone | zero is unknown; other sample 100.37 m | rejected |
| Two padding bytes in the row | zero is unknown; other sample 5.0 m | rejected |
| Extra byte beyond declared row | `invalid_image_bytes` | rejected |

All rejections are `evidence_mismatch`, with no returned evidence or task/passport,
policy-revision or expiry metadata. All authority flags remain false. These values
are arithmetic expectations for synthetic bytes, not accuracy or range measurements.
The corpus inventory and expected decoder outcomes are independently asserted.

## Verification and remaining gates

Seven consumer methods and 60 related methods pass, with zero skips. Ruff checks and
format verification, Bandit and diff checks pass. The two initial failures are retained
as missing-coverage evidence, not described as a production RED. The existing CI
consumer job already includes these test and fixture paths. No full repository suite,
new installed-distribution run, hardware test or hosted CI result is claimed here.
See the [result record](p16-sensor-encoding-v3-results.json) for source and log hashes.

The safe embedded requirements are only partially exercised: versioned source pins,
encoding validation, corruption rejection and non-authorizing results have focused
software evidence. Device authorization, freshness, clock reconciliation, watchdogs,
target timing, toolchain certification and P19 installed acceptance/help remain
unfinished or unqualified. These checks do not establish MLS, CNSA, Link 16, vendor
protocol support, five-nines availability or a hardware safety case.
Insufficient information for tactical deployment.

Next: inspect the available published P3/P14 interfaces for a bounded P16 consumer
fixture. A historical phase-1 file named `p14.json` is not a measurement-result
contract; no such contract was identified in the cached-main search. Continue
independent software work without duplicating the producer or claiming integration.
