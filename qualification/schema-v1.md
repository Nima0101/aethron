# Qualification declaration schema v1

Version 1 is a software-only evidence declaration contract. Future semantic or
bound changes require a new version; it does not supersede frozen runtime gates.

Input is UTF-8 JSON bytes, at most 65,536 bytes and nesting depth 8. Reject
duplicate or unknown keys at every level, nonfinite numbers, booleans as numbers,
fractional timestamps and unsupported versions. Every listed field is required.
Hashes are exactly 64 lowercase hexadecimal characters. Tokens match
`[a-zA-Z0-9_-]{1,64}`. Times are integers in `0..2^53-1000` milliseconds in one
declared boot-local monotonic domain; offsets can be negative within the same
magnitude. No wall-clock conversion or cross-boot comparison is supported.

Root: `version` (integer 1), `rig`, `capture`, `records`.

- `rig`: `id` (token), `configuration_sha256` (hash), `sensors` (1–5 entries).
  Each sensor has exactly `id` (unique token), `kind`
  (`rgb/lwir/radar/depth/nir`, unique within the rig), `device_sha256` (hash),
  `mount_sha256` (hash). Digests bind declarations; they do not prove exact SKU
  identity or a calibrated mounting configuration.
- `capture`: `clock_domain` (token), `start_ms`, `end_ms`. Start must not exceed
  end. Trusted evaluation `now_ms` is separate, never read from the document.
- `records`: 0–15 entries. Each has exactly `sensor_id` (rig sensor token),
  `kind` (`calibration/clock/environment`), `evidence`
  (`synthetic/recorded/external_unverified`), `artifact_sha256` (hash),
  `rig_sha256` (hash), `clock_domain` (token), `data` (object below).
  At most one record per sensor/kind. No URLs, paths, free text, identities,
  embeddings or approval flags are accepted. All three kinds are required per
  sensor for declaration checks to pass. Empty records produce explicit missing
  findings, never a qualified result.
- Calibration `data`: `valid_from_ms`, `valid_until_ms`. The interval must be
  ordered and cover the entire capture interval.
- Clock `data`: `at_ms`, `offset_ms` (signed integer), `uncertainty_ms`
  (nonnegative integer). Offset is sensor clock minus reference clock; `at_ms`
  is expressed in the declared reference domain. Each sensor's absolute offset
  plus uncertainty and each pair's offset difference plus both uncertainties
  must be <=50 ms. This is a conservative software consistency check against the
  frozen skew budget, not an independently measured drift guarantee. The check
  assesses the stated capture end only; no extrapolation over the interval.
- Environment `data`: `at_ms`, `lighting`
  (`daylight/low_light/near_dark/zero_visible`). Sensor lighting declarations
  may differ; no sensor usability, detection or absence is inferred from them.

The rig digest is SHA-256 of UTF-8 JSON for the entire `rig` object serialized
with sorted object keys, compact separators and ASCII escapes, no trailing
newline. Array order is significant. Every record must bind this digest and the
capture clock domain. Calibration interval or binding disagreements produce
findings. Clock/environment `at_ms` must lie in the capture interval and be at
most 100 ms before capture end. Capture end must not be future or more than
100 ms before the evaluation instant. Inclusive timing/skew bounds follow v3;
this harness cannot satisfy v3 runtime admission on behalf of sensors.

Output: `version` (1), `input_sha256`, `declaration_checks_passed` (boolean),
`sensor_count`, `record_count`, `evidence_counts` (all three evidence enum keys),
`findings` (sorted unique fixed codes), `artifacts_verified` (always false),
`physical_qualification_passed` (always false), `physical_status`
(always `blocked_external_evidence_and_review`). Input digests refer to exact
bytes, so differently spaced inputs intentionally produce different bindings.
Missing/stale/bad-binding failures are retained even when other records pass.
