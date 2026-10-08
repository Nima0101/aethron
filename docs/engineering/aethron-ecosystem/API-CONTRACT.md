# API contract — SPEC ONLY except the existing core example

## Compatibility boundary

Core distribution is currently `aethron==0.2.0`. Frozen sensor wire protocol is **3**; proposed edge HTTP API is **/api/v1**; proposed edge distribution is **aethron-edge 0.1.0**. These are independent versions. Do not rename the existing package or put networking inside `aethron/`. Unknown fields and enum values fail closed in v3. No body field can claim `hardware_verified`; qualification lives in a signed external evidence record.

Existing executable library path:

```python
from aethron.temporal.session import Session
from pathlib import Path
session = Session()
first = Path("examples/temporal-blackout.jsonl").read_bytes().splitlines()[0]
result = session.step(first, now_ms=0)  # fixture clock only; live uses trusted monotonic time
session.close()
```

For full deterministic offline data use the existing `python3 -m aethron replay examples/temporal-blackout.jsonl`. Replay accepts only synthetic/recorded provenance, ≤300 frames and ≤30 s; it never self-certifies hardware.

## Proposed installed invocation

The following commands/modules do not exist yet. Implement and exercise them in Phase 1 before publishing a runnable quickstart:

```sh
python -m pip install --no-index --find-links wheelhouse aethron-edge==0.1.0
python -m aethron_edge doctor --config examples/edge-replay.json
python -m aethron_edge replay --config examples/edge-replay.json
python -m aethron_edge serve --config examples/edge-local.json
python examples/clients/observe.py --config examples/client-local.json
```

Public `pip install aethron-edge==0.1.0` is a future release intention, not a verified package/index reservation. `doctor` reports installed drivers/providers and evidence level without opening cameras unless `--probe` is explicitly requested. Configuration defaults: loopback host `127.0.0.1`, port `8765`, four-session limit, no raw recording/cloud upload, explicit source allowlist, token read from an owner-only file. A port conflict fails, never binds an unexpected interface.

## HTTP operations

| Method/path | Input / success | Failure behavior |
|---|---|---|
| GET `/healthz` | process liveness only, fixed minimal body | Never means sensing healthy |
| GET `/api/v1/capabilities` | authenticated runtime/driver/provider versions, protocol=3, qualification refs | Report unavailable rather than silently emulating |
| POST `/api/v1/replays` | raw NDJSON bytes, ≤300 lines/30 s, ≤20 MiB total; bounded per-line v3 parser | 413 bound exceeded; 422 invalid; clear state and fixed error |
| POST `/api/v1/sessions` | `{ "source_profile": "front-retrofit", "contract": "warn" }` | Profile must be local allowlisted config; 409 unavailable; 429 capacity |
| GET `/api/v1/sessions/{session}/snapshot` | envelope with actual core result | 404 unknown/expired session; no history lookup |
| GET `/api/v1/sessions/{session}/events` | SSE latest snapshot and health/gap events | Slow readers disconnected; no persisted event backlog |
| DELETE `/api/v1/sessions/{session}` | 204; release this viewer handle only | Idempotent 204 for already closed session owned by caller |

No HTTP endpoint for arbitrary URLs, files, imports, model upload, live frame upload, commands or actuator control. POST attaches an observation handle to a locally configured, already supervised pipeline; an administrator chooses source addresses outside the API. The appliance boots that pipeline without any POST, connected viewer or active subscription. DELETE/disconnect cannot stop appliance workers; core track erasure remains governed by core expiry and supervisor shutdown. This removes a network clock trust ambiguity in Phase 1. Remote authenticated observation ingestion is a later contract with measured clock mapping, not a generic POST `/frames` shortcut.

Replay output uses virtual time and `evidence=recorded` or `synthetic`; it must be visibly separated from live sessions. API library signature proposed: `replay_bytes(data: bytes) -> ReplayReport`, with `ReplayReport` containing ordered output snapshots and counts, no live token IDs. Runtime session service signature: `open_session(profile: str, contract: Contract, principal: Principal) -> SessionHandle` (attach viewer; contract must match configured pipeline); `snapshot(handle: SessionHandle) -> SceneEnvelope`; `close_session(handle: SessionHandle) -> None`.

## Strict types and example messages

All object schemas are closed (`additionalProperties: false`), all fields listed are required unless explicitly nullable. Integer counters reject booleans, floats and strings. No NaN/infinity, duplicate keys, arbitrary nested metadata or class IDs from vendors. Source profiles are ASCII `[a-z0-9-]{1,48}`; session tokens are random 128-bit or stronger, erased at close, and never carry a person identity. Core generates its own ephemeral track IDs, independent of transport session handles.

Valid v3 input example (sensor registration/calibration is synthetic here):

```json
{"version":3,"at_ms":1000,"lighting":"zero_visible","evidence":"synthetic","mode":"direct","contract":"warn","scene_break":false,"sensors":[{"kind":"lwir","at_ms":1000,"quality":"valid","calibration_until_ms":2000,"registered":true,"detections":[{"class":"person","box":[0.2,0.3,0.1,0.2],"score":0.8,"variance":0.001,"range_m":null}]}],"ego":{"dx":0,"dy":0,"variance":0,"valid":true}}
```

This is the existing v3 shape; repeat at 1050 ms for the second observation to confirm a track. LWIR alone cannot invent metric range. The server passes the *unchanged bytes* to core validation. `now_ms` is never in the HTTP request.

Proposed empty/expired scene event (illustrative envelope; `result` is the exact core output, frozen from a real call during Phase 1 rather than hand-invented here):

```json
{"api_version":"1","kind":"health","sequence":8,"session":"example-opaque-token","reason":"source_lost","scene_state":"UNKNOWN","retryable":true}
```

`SceneEnvelope` fields: `api_version: Literal["1"]`, `kind: Literal["scene"]`, `sequence: int[0..2^53-1]`, `session: string`, `clock: {domain: Literal["edge_monotonic"], emitted_ms: int, valid_for_ms: int[0..100]}`, `result: V3Snapshot`. Freeze `V3Snapshot` against actual `Session.step`/watchdog outputs; do not silently remodel recommendations or track states in a client. If there are no current supporting claims, `valid_for_ms=0`. Additional transport `HealthEvent` as above uses reason enum `source_lost|clock_untrusted|calibration_expired|model_error|overload|stream_gap|closed`; it cannot extend a scene lease. Error response: `{ "api_version":"1", "error":"invalid_request", "retryable":false }` with no payload echo. Other error enums: `unauthorized`, `forbidden`, `capacity`, `source_unavailable`, `not_found`.

SSE `event: scene`, `event: health`, `event: gap`; data is one bounded UTF-8 JSON object. One pending event/subscriber, ≤64 KiB/event. Increasing sequence is scoped to the transport session. No `Last-Event-ID` history replay: reconnect emits a gap followed by a newly computed snapshot, never old boxes. On disconnect the client immediately displays UNKNOWN; otherwise it expires based on conservative measured clock offset/RTT bounds. `valid_for_ms` alone is insufficient across a delayed network: clients unable to bound transit may display a timestamped observation, but cannot label it current. Native clients use a monotonic timer even when no new events arrive. The proposed service watchdog polls at ≤20 ms; frozen evidence expiry is still 100 ms and must also be enforced at read/render time.

WebSocket is deferred: SSE covers server-to-client observations and avoids two-way command semantics. If later required for binary transfer, write a separate protocol with bounded buffers/auth/reconnect before implementation. gRPC is reserved for measured native IPC need; ROS 2 bridge is separately scoped.

## Plugin manifest and frame boundary

`SourceInfo`: driver ID/version, modality, encoding, negotiated dimensions, supported clock origin, frame-rate ceiling, calibration requirement and `qualification_ref` nullable. No serial/location in public telemetry. `FrameEnvelope`: bounded buffer handle, width/height/stride/encoding, `modality`, `sequence`, `capture_ns`, `receive_ns`, `clock_id`, `clock_uncertainty_ns`, `calibration_id`, `quality`. Capture time can be null; such frames are usable for delayed preview, not fresh v3 evidence until latency bounds are established.

Manifest fields: `manifest_version=1`, `driver_id`, exact distribution version/digest, `abi=1`, supported OS/arch, modalities, permissions (`camera`, selected `network_source`, optional read-only telemetry), maximum buffer bytes, timestamp origin, license reference and configuration-schema digest. Manifest is administrator-installed and hash verified; Python entry-point discovery does not auto-load installed packages. No person ID, appearance feature, biometric field or cross-camera association key is permitted. Multiple independent cameras run separate scene sessions unless they are geometrically calibrated views of the same immediate scene under the existing permitted fusion contract.

## Auth, privacy and lifecycle

Loopback still requires a random bearer token; reject unexpected Host/Origin and disable CORS by default to resist malicious websites and DNS rebinding. No credentials in query strings or source URLs in logs. Fetch-based SSE permits Authorization headers; browser EventSource requires a reviewed same-origin cookie alternative with CSRF controls, not token URLs. Non-loopback binding requires explicit config, TLS and authenticated per-device principals; enterprise reverse proxy may terminate TLS with a protected local upstream. Scope tokens as `observe`, `session:manage` and local-only `configure`; authorize every session lookup. Persist configuration, aggregate fault counters and evidence digests only. Reset/close erases track state. Process restart creates new IDs and UNKNOWN until fresh data arrives.

## Appliance lifecycle binding

The [appliance supervisor](APPLIANCE-RUNTIME.md) owns the pipeline's configured contract. Viewers cannot change it through POST or prolong core track lifetime by subscribing. `close_session(handle)` closes only a viewer handle; `ApplianceSupervisor.shutdown(reason)` closes core sessions and workers on authorized local maintenance or host shutdown. Four observation handles and eight subscribers are admission defaults, separate from at most four configured pipelines. Unattended local indicator/API state is generated even with zero handles. Replay jobs remain bounded separate sessions and never replace the boot pipeline.

Add a local-only supervisor CLI `aethron-edge run --config appliance.json` as the boot service entry point. `serve` remains a developer/service wrapper around the same supervisor and optional HTTP interface; no separate mock runtime. Public capabilities include `runtime_mode=appliance|interactive|replay` and scoped qualification references in a versioned closed schema to be finalized in P1.2, never extra fields inside v3. An API restart must not reset a healthy independently supervised inference worker merely because a viewer disconnected.
