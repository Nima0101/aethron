# Campaign bundle stdin framing v1

From the source checkout, `python -m qualification.campaign_bundle_cli` reads one
binary frame from stdin, requires EOF, and emits the existing
[bundle report](campaign-bundle-v1.md) as compact, sorted-key JSON plus one newline.
The command accepts no arguments. It opens no named file, device or network and
does not sample a clock. A shell may redirect an authorized local frame to stdin.

All integers are unsigned, big-endian, without padding. A **blob** is a four-byte
length followed by exactly that many bytes. The fields occur in this order:

| Field | Encoding and bound |
|---|---|
| Magic | Literal ASCII `AETHRON-QUALIFICATION-BUNDLE-V1` followed by LF |
| Plan | Blob, at most 65,536 bytes; existing strict campaign JSON contract |
| Domain reference | Blob, at most 1,048,576 opaque bytes |
| Procedure reference | Blob, at most 1,048,576 opaque bytes |
| Capture count | Four-byte integer, 0–64 |
| Each capture's case ID | Blob, 1–64 ASCII bytes matching `[a-zA-Z0-9_-]+` |
| Each capture's evaluation instant | Eight-byte integer, 0 through `2**53 - 1000` |
| Each capture's manifest | Blob, at most 65,536 bytes |
| End | EOF immediately after the last capture |

The last three capture fields repeat exactly the declared count. Length limits
are checked before reading the associated payload; count is checked before any
capture is read. Short reads are accumulated. Truncated fields, a wrong magic,
oversized lengths/count, trailing bytes, invalid case IDs/instants, invalid plans
and unexpected arguments fail with exit 2, fixed `invalid_campaign_bundle` on
stderr and no report. A structurally framed but invalid capture manifest retains
the campaign API's negative finding and exit 1; it is not silently dropped.

Exit 0 requires both declaration coverage and matching reference bytes. Exit 1
retains the complete valid negative report. Neither exit qualifies hardware,
authenticates evidence, approves domain/procedure content or verifies capture
artifact bytes. The supplied evaluation instant is replay data, not a trusted
clock sample. Capture multiplicity and instants retain the API's commitment
semantics. Original plan and manifest bytes are passed unchanged, including JSON
whitespace; opaque reference bytes are never decoded. There is no new signature,
frame commitment, persistence, authorization or deduplication mechanism.

The input payload ceiling is 6 MiB plus a 65,536-byte plan and bounded framing
(magic, four lengths/count and at most 64 case IDs, instants and blob lengths).
This is not a measured RSS ceiling: accumulation, immutable conversion, parsing
and reports allocate additional memory. No unbounded stream read is used. Reads,
EOF detection, stdout writes and flush can block indefinitely; the invoking
process owns deadlines and supervision. Output is not atomic: an I/O failure can
leave partial output, so consumers must require successful exit and complete JSON.
Writable stderr is required to deliver the fixed diagnostic. Digests and counts
are linkable, and the unauthenticated report must not be treated as an approval.

## Technology decision — 2026-10-10

Requirements are bounded local byte transport into the reviewed synchronous
bundle API, exact integer/byte fidelity, early length rejection, deterministic
report serialization and no external service or hard deadline. The candidate
search includes binary language facilities and interchange formats:

| Candidate | Decisive fit and tradeoff |
|---|---|
| Python `struct` plus bounded reads | Explicit standard-width big-endian integers and direct immutable-byte transfer to the validators; no semantic re-encoding at the adapter boundary. |
| Go `encoding/binary` | Suitable fixed-width byte decoding and native executables. A full Go validator could also preserve bytes; this adapter alone would still need an additional validator binding/transport. No standalone-native deployment requirement currently selects it. |
| Rust integer decoding / `byteorder` | Static ownership and explicit-endian input are credible for native integration. It can preserve the contract with a binding or migrated validators; no measured memory/latency deficit currently favors that change. |
| Erlang bit syntax | Direct binary pattern matching and length guards suit framed messages; process isolation suits a supervised service. This single synchronous invocation has no distributed actor or service supervision requirement. |
| CBOR byte strings, or JSON with base64 | Established richer interchange is credible when external producers require it. Here it adds generic parser/encoding rules beyond the fixed fields; no such ecosystem contract has been specified. |

**SELECT Python `struct` with the specified frame.** The decision favors direct
byte-preserving composition and explicit pre-read limits, not familiarity or
installation convenience. Native deployment, a published external interchange
contract, service isolation or measured target-resource constraints reopen it.
No cross-language performance ranking or hard real-time claim is made.

Official sources consulted:
[Python standard sizes and byte order](https://docs.python.org/3.13/library/struct.html),
[Go binary encoding](https://pkg.go.dev/encoding/binary),
[Rust byteorder](https://docs.rs/byteorder/latest/byteorder/), and
[Erlang bit syntax](https://www.erlang.org/doc/system/bit_syntax.html).
Those sources support mechanism descriptions; the selection is a requirements
judgment. Executable tests check short reads, every truncation of the small
synthetic frame, early size rejection, opaque reference bytes, exact limits,
commitment fidelity and simultaneous negative evidence. The frozen synthetic
report is `evidence/synthetic-campaign-bundle-v1.json`; it provides no physical
qualification evidence.
