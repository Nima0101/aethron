# Offline intensity recording pin

The existing `aethron_edge.sensors.intensity_inspect` command accepts the optional
`--expected-recording-sha256` argument. Supply an independently obtained lowercase
64-character SHA-256 digest to require that the complete inspected file matches
the intended recording. The required calibration pin remains separate.

```sh
python -m aethron_edge.sensors.intensity_inspect \
  --recording recording.bin --calibration calibration.json \
  --expected-calibration-sha256 "$CALIBRATION_SHA256" \
  --expected-recording-sha256 "$RECORDING_SHA256" --pixel 1 0 --max-frames 2
```

The file digest covers every consumed byte: length prefixes, JSON headers,
payloads and padding. All packets must still pass their existing checks. A
matching digest cannot admit malformed data. Conversely, valid packet checksums
cannot admit a different valid recording or a shortened valid prefix when a pin
is supplied. The command emits no stdout until it has parsed the complete file
and checked the pin. A mismatch returns exit 2 and the fixed
`invalid_intensity_inspection` error without echoing inputs.

Successful output remains the existing version 1 document, byte-for-byte the same
with or without the optional pin for identical arguments and input. Omitting the
pin preserves the previous behavior. No new report fields, evidence authority,
device access or temporal linkage are introduced. A digest checks equality with
the supplied value; it is not a signature, ownership proof, physical calibration
verification or live-evidence grant. The containing directory must remain trusted.

## Constraints and implementation choice

This Linux offline path must retain the 64 MiB recording ceiling, 300-frame and
30-second replay limits, at most 64 selected pixels, one pending input packet,
and no partial output. It must verify the bytes actually decoded on the same
descriptor, without an extra file pass or whole-file allocation. Hashing adds
constant-size state to the existing bounded reader; remapping limits and error
handling stay unchanged. No latency or hardware qualification is claimed.

The [standard hashlib interface](https://docs.python.org/3/library/hashlib.html)
specifies that successive digest updates hash the concatenation of supplied
bytes. Its `file_digest` helper may bypass the Python reader through the file
descriptor. Explicit SHA-256 updates therefore fit this parser boundary; using
that helper or a separate file-hashing process would not share the bounded read
checks and exact byte stream. This is a small integration with the existing
decoder, with no new runtime dependency or toolchain.

The focused regression exercises the real CLI with a valid two-frame mono16
recording, checks identical pinned/unpinned counts, rejects malformed and wrong
pins, rejects a valid shortened file, and rejects malformed trailing bytes even
with a matching full-file digest. Existing calibration, count/mask, frame-limit
and corruption tests remain applicable. Evidence is retained in
[the focused check record](evidence/phase2/intensity-recording-pin.json).
