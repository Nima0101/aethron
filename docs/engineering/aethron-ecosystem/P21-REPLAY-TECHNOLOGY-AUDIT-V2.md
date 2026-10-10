# P2.1 C02 binary replay — retrospective audit policy v2

Decision: **KEEP Python strict header validation and incremental framing; replace
unconditional buffer copying with a checked immutable complete-read path.** C01
and C02 are assessed; C03–C09 remain pending. Forward expansion stays paused.
This reassesses both original v1 and the already-built variable-count v2 reader.

## Operational constraints

A Linux offline reader must consume existing length-prefixed UTF-8 JSON plus raw
payload bytes, not change the recording format. Headers are capped at 16 KiB;
validated layouts bound each payload to 8 MiB and clouds to 4096 samples. The
reader is incremental and does not itself bound total stream length. Appliance
and inspector callers own whole-recording limits and digest admission. A valid
prefix can be yielded before a corrupt suffix fails; this is not whole-file
certification. There is no hard-real-time or physical qualification claim.

Stream adapters may implement only bounded `read(n)`, with short reads and no
seek, descriptor or `readinto` method. EOF before a prefix differs from truncated
prefix/header/payload. Invalid read types and overlong responses fail closed.
Headers require exact nonnegative integers through 2^63−1, no boolean numerics,
no duplicate decoded keys at any object depth, strict UTF-8 and closed schemas.
Checksums detect corruption, not authenticity. v1 fixes layout; v2 permits only
cloud dimensions/padding to vary while keeping format/provenance, increasing
sequence and nondecreasing recorded acquisition time. Frames never become live.

These constraints favor bounded ownership and precise admission over generic
network concurrency or indexing. The shared host has 6.3 GiB RAM. No device SDK,
network transport, native pointer interface or background service is required.

## Domain candidates and evidence

| Candidate | Decisive properties under these constraints |
| --- | --- |
| Python binary streams + strict JSON/Pydantic | Exact integers, duplicate-key hook and bounded read-only adapters; complete immutable reads can transfer ownership without intermediate payload copies. Executed production/contract and allocation tests. |
| Preallocated `readinto` | Can reduce fragmented-read allocation, but requires an optional stream capability and a final copy to immutable bytes. Executed against identical synthetic bytes, including an unfavorable result for the selected fallback. |
| Node Buffer/fs + JSON parser | Native bounded binary I/O is viable. Stock JSON.parse fails duplicate-key and int64 conformance vectors. A token-level duplicate-aware parser and exact integer representation could correct it; this experiment does not rule out JavaScript. No measured full-reader advantage justifies that additional runtime here. |
| C# System.IO.Pipelines + Utf8JsonReader | Segmented input, flow control and Int64 token extraction are credible alternatives beyond the incumbent language. Duplicate tracking/closed schemas and owned immutable results still need explicit application logic. Network concurrency and buffer lifetimes across consumers are not requirements of this single offline stream. Source comparison only. |
| Java DataInputStream + Jackson streaming | `readFully` provides exact-length/EOF behavior; Jackson offers strict duplicate detection. This can implement the contract with a managed runtime and explicit safe binding. Source comparison only; no JVM speed or memory inferiority is claimed. |
| MCAP storage libraries | Useful robotics container with record framing, indexes, chunks and checksums. It is a different wire format, so cannot replace the frozen v1/v2 reader without retaining an adapter. No recording conversion or ROS expansion is required by C02. |

Primary sources reviewed for this decision:

- [Python binary I/O](https://docs.python.org/3/library/io.html) describes bounded
  reads, short reads and optional stream capabilities; [JSON hooks](https://docs.python.org/3.13/library/json.html)
  provide ordered decoded key pairs and exact integer conversion. These are the
  actual mechanisms used, not evidence that any default JSON parser is strict.
- [Node fs reads](https://nodejs.org/api/fs.html#fsreadsyncfd-buffer-offset-length-position)
  and [ECMAScript JSON.parse](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.parse)
  establish the native read and stock parser candidates. Executed Node v22.23.2
  accepted three duplicate-key forms and rounded 9223372036854775807; all four
  counterexamples are retained.
- [.NET pipelines](https://learn.microsoft.com/en-us/dotnet/standard/io/pipelines)
  exposes segmented buffering/flow-control responsibilities;
  [Utf8JsonReader.GetInt64](https://learn.microsoft.com/en-us/dotnet/api/system.text.json.utf8jsonreader.getint64?view=net-9.0)
  supplies an exact integer extraction path. No .NET toolchain was installed.
- [Java DataInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html)
  defines `readFully`; [Jackson's primary source](https://raw.githubusercontent.com/FasterXML/jackson-core/2.18/src/main/java/com/fasterxml/jackson/core/StreamReadFeature.java)
  documents explicit duplicate detection. The javadoc mirror request failed;
  the upstream source was used instead. No Jackson dependency was installed.
- [MCAP specification](https://mcap.dev/spec) defines its container structure;
  format compatibility, not an unsupported performance claim, rules it out as
  a replacement for this existing reader.

## Executable comparison and implementation

The bounded probe uses 1 MiB of synthetic bytes, a memory stream, a temporary
file and a stream returning 4096-byte fragments. Fifteen rotated samples compare
the retained baseline, a direct-read prototype, preallocated readinto and actual
production. Timing and traced allocation runs are separate. It measures the I/O
ownership mechanism, **not** complete replay latency, RSS or all runtime memory.

| Final traced allocation peak | Baseline | Production | readinto |
| --- | ---: | ---: | ---: |
| Memory | 2,097,270 B | 144 B | 2,097,330 B |
| File | 3,145,879 B | 1,049,065 B | 2,097,330 B |
| Fragmented | 2,204,828 B | 2,204,828 B | 2,097,330 B |

For file reads, median measured CPU was 2.816 ms baseline, 0.983 ms production,
1.351 ms readinto. Fragmented reads favored readinto (1.936 ms vs 2.718 ms
production); that negative result is preserved. The selected path removes two
payload-sized copies for ordinary complete file reads, while retaining every
read-only adapter and the existing fragmented semantics. An optional readinto
fast path is not selected: its demonstrated fragmented benefit does not remove
the immutable-result copy or justify a second adapter protocol for this bounded
file-oriented deployment. It remains a candidate if fragmented input becomes a
measured production bottleneck.

The implementation checks type, requested length and EOF before accepting an
exact `bytes` result. It does not broaden acceptance to bytearray or memoryview;
bytes subclasses still use the accumulation path and produce plain bytes.
Zero-length cloud payloads make no stream read. Layout/hash validation, header
validation, continuity, public exceptions and version semantics remain intact.

The decision is based on measured copy elimination plus semantic compatibility
and deployment footprint. It is not based on installed tools, familiarity or
rewrite cost. Source-only candidates remain feasible; no unmeasured universal
performance comparison is claimed. No threshold or frozen protocol was tuned.

## Verification and limits

The memory regression failed before implementation: 2,097,302 traced bytes for
an already-owned 1 MiB input, exceeding the input-sized temporary-allocation
budget. It passes after the change. Additional tests cover non-bytes/overlong
reads, fragmented EOF, zero-length input, nested/escaped duplicate keys and
adjacent int64 timestamps at the limit. Existing checksum, v1/v2 continuity,
corruption and offline inspector tests remain part of the focused selection.

[Probe instructions](../../../scripts/probes/sensor_replay_audit/README.md) and
[executed evidence](evidence/phase2/technology-v2-replay.json) retain the RED
result, before/after measurements, Node counterexamples and exact check results.
Historic T10 latency and signed radar startup failures are not cleared by this
work. Full hosted checks and external physical/legal gates remain separate.
