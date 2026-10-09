# Passive MAVLink observations (P3.1 development)

The optional installed `aethron_edge.telemetry.mavlink` adapter decodes real MAVLink 2 common-dialect ATTITUDE (30) and LOCAL_POSITION_NED (32) packets using pymavlink 2.4.50. It is a diagnostic observation interface, not perception evidence or an autopilot controller. No command, heartbeat, ACK, rate request or TIMESYNC is transmitted. It neither enables telemetry streams nor changes flight-controller configuration.

Install the separately built core and edge wheels first. For the locally tested CPython 3.13/macOS ARM64 SDK closure:

```sh
python -m pip install --require-hashes -r integrations/edge/requirements-mavlink-macos-arm64-py313.lock
python -I -m unittest discover -s tests/mavlink -v
python tests/mavlink/fuzz_signing.py  # 60-second campaign against the installed wheel
```

Other platform installations can resolve the pinned `aethron-edge[mavlink]` extra, but require their own artifact locks, installed tests and qualification. The SDK is not included in the default edge install or appliance images.

```python
from aethron_edge.telemetry.mavlink import PassiveTelemetry, UdpTelemetry

source = PassiveTelemetry(system=1, component=1)
with UdpTelemetry(source, port=14560) as receiver:
    status = receiver.poll()  # one datagram, <=20ms socket wait; no transmission
    print(status.state, status.reason)
```

An operator-owned local simulator/router must already provide exactly one allowed MAVLink 2 packet per UDP datagram for this original API. The socket binds only to `127.0.0.1`; direct serial, WAN, MAVLink 1 and vendor dialects are not implemented. Multi-packet datagrams require the opt-in v1 wrapper below. `PassiveTelemetry.ingest(bytes)` also supports explicit in-process wire replay. Poll repeatedly under the caller's supervisor, or configure the signed-only appliance integration described below. PX4/ArduPilot SITL and physical firmware tuples remain untested.

### Opt-in multi-packet datagrams (v1)

The separate `aethron_edge.telemetry.datagram_v1` API accepts bounded concatenated
MAVLink 2 packets from an already configured local simulation/router feed:

For Linux x86_64/CPython 3.13 with glibc>=2.28, install the optional wire SDK using
`python -m pip install --only-binary=:all: --require-hashes -r integrations/edge/requirements-mavlink-linux-x86_64-py313.lock`.
The core and edge packages must already be available as described above.

```python
from aethron_edge.telemetry.datagram_v1 import DatagramTelemetryV1, UdpTelemetryV1
from aethron_edge.telemetry.mavlink import PassiveTelemetry

decoder = PassiveTelemetry(system=1, component=1)
with UdpTelemetryV1(DatagramTelemetryV1(decoder), port=14560) as receiver:
    status = receiver.poll()
```

Pass an explicitly provisioned `SignedTelemetry` instead to retain signed-only
authentication and persisted replay protection. The wrapper exclusively owns
its decoder; do not share it with other readers. It checks complete framing
before decoding, accepts at most 16 packets/4480 bytes, and stops on any rejected
packet. Heartbeats, commands and other non-allowlisted messages still cause
UNKNOWN; the caller must supply an already filtered feed. No stream requests or
other packets are sent. No partial packets are retained across datagrams.

Each framed batch replaces previous samples and has a 100 ms receipt deadline
including decoding/journal time. Source timing, signing authority and replay
checks remain in force. A later failure never rolls back committed signing
counters. Socket queue age and physical capture freshness remain unknown.
The original single-packet API and appliance worker are unchanged; this API is
not automatically enabled by appliance configuration. Synthetic wire/loopback
tests do not qualify a PX4/ArduPilot firmware tuple or actual SITL execution.
See the [v1 contract and technology decision](../../../../docs/architecture/mavlink-datagram-v1.md).

## Contract and failure behavior

- The fixed system/component tuple is a routing filter, **not authentication**. Unsigned samples always carry `external_unverified`, `authenticated=False`, `capture_ns=None`; status always has `perception_eligible=False`. `PassiveTelemetry` refuses signed traffic; the separate opt-in `SignedTelemetry` interface below requires provisioned trust and a replay journal.
- ATTITUDE carries body Euler angles in radians and angular rates in rad/s. LOCAL_POSITION_NED carries an unregistered local NED position/velocity in m and m/s. The six `fields`, `values` and `units` entries correspond by index. No coordinates are converted to camera displacement, world coordinates or inferred object tracks.
- Two immutable latest-sample slots, no trajectory/history. A local monotonic receipt older than 100ms expires on `snapshot()`/`poll()`, including no-traffic timeouts. This is a receipt TTL, **not** source measurement freshness: remote boot timestamps remain unmapped and router/socket buffering is unqualified. Never substitute it for frozen v3 exposure-age/calibration rules.
- Input <=280 bytes, exactly one packet, pinned payload layout/CRC, finite values, sequence progression modulo256 (delta1..127), strictly advancing boot time per message type. Malformed, foreign-sender, unsupported or reordered input clears observations. A boot reset/wrap/duplicate acquisition timestamp or local-clock rollback latches UNKNOWN until a fresh instance. Signed/extension flags are refused. CRC-bypass SDK configuration and SDK version mismatch prevent construction.
- `close()` erases state and latches closed. Use a single owner/thread; callers retain responsibility for overall polling/resource limits. Unsigned traffic remains spoofable/replayable and must not grant capability authority even when these checks pass.

## Provenance and license boundary

Official sources retrieved **2026-10-09**: [pymavlink usage and direct dialect API](https://mavlink.io/en/mavgen_python/), [common message fields](https://mavlink.io/en/messages/common.html#ATTITUDE), [MAVLink 2 serialization/trailing-zero rules](https://mavlink.io/en/guide/serialization.html), [pymavlink 2.4.50 artifact metadata](https://pypi.org/pypi/pymavlink/2.4.50/json). The PyPI dialect is generated from the ArduPilot MAVLink fork; this is not a claim that all current upstream definitions match. No third-party SDK source is copied into AETHRON.

The installed distribution declares pymavlink LGPLv3, fastcrc 0.5.0 MIT, and lxml 6.1.3 BSD-3-Clause with additional bundled-component notices. Preserve all wheel license notices on redistribution; a project-owned commercial license does not replace third-party terms. Exact local artifact and notice hashes are retained with the development evidence. This checkpoint is not release or hardware qualification.

## Signed receive-only interface

`aethron_edge.telemetry.signing` adds `SigningTrust`, `provision_replay` and `SignedTelemetry`. The constructor accepts the same system/component and local clock as the passive decoder, plus `trust=` and `replay_path=`. `UdpTelemetry` accepts either decoder and remains receive-only.

`SigningTrust(key, link_id, timestamp_floor, issued_ns, valid_until_ns)` requires a securely provisioned 32-byte shared key, one link ID, an authoritative MAVLink timestamp floor and a validity interval in the **current host boot's monotonic clock**. The floor is the exclusive lower bound at `issued_ns`, measured in MAVLink's 10µs units from its 2015 epoch; it is not the packet's `time_boot_ms` or camera exposure time. Obtain these values from a trusted offline provisioner/RTC and persisted state, never by trusting the first incoming packet or copying an example key. Renew the local anchor after host reboot. No key provisioning message or automatic key learning is sent.

Before first use, explicitly call `provision_replay(path, trust, system=..., component=...)` in an existing private POSIX directory owned by the service user (mode0700). This creates a mode0600 SQLite file exclusively; it refuses to overwrite existing state. Normal startup only opens an existing journal, validates its ownership/mode, and binds it to the key and exact system/component/link tuple. Reuse that journal across receiver/process restarts. Missing, replaced, malformed or unwritable state fails closed. Key/stream rotation needs separate explicit provisioning, not deletion/recreation during normal startup. Windows storage support remains pending.

Only signed packets are accepted in this mode. Signature bytes use constant-time comparison, CRC/payload checks still apply, and no fallback accepts unsigned or bad signatures. Each SDK decode is isolated to prevent failed signature attempts from advancing SDK replay state. After semantic validation, a serialized SQLite transaction commits a strictly increasing signature timestamp **before** exposing an observation; competing receivers share this counter. No payload, location, key or trajectory is stored. Authority expiry withdraws observations even without traffic; timestamp/authority limits never become v3 measurement freshness evidence.

The provisioned timestamp advances with local monotonic elapsed time. This adapter additionally requires every signed timestamp within ±60s of that anchor and above the provisioned floor; this bounded policy can refuse otherwise signed upstream traffic and must be qualified for a specific stack. Remote boot resets still require a new receiver session; the persisted signing counter survives. The 100ms receipt TTL still applies independently.

Authenticated samples expose `authenticated=True`, `link_id`, and `signature_timestamp`, while retaining `external_unverified`, `capture_ns=None`, `OBSERVED_UNVERIFIED`, and `perception_eligible=False`. A shared-key signature proves possession of the provisioned key, not unique hardware identity, confidentiality, calibration or trustworthy measurement timing. Filesystem rollback by the trusted journal owner and physical power-loss durability are not qualified; protect provisioning/state with the appliance's host trust boundary. Python key references are released on close, with no guaranteed memory zeroization. Full release/hosted/SITL and physical qualification remain pending.

Signing references retrieved 2026-10-09: [official packet/signature and timestamp rules](https://mavlink.io/en/guide/message_signing.html), [pymavlink signing interface](https://mavlink.io/en/mavgen_python/message_signing.html). Tests use public synthetic keys and real SDK-encoded wire bytes; no real device secret is committed.

## Process-owned telemetry worker — development checkpoint

`aethron_edge.telemetry.worker.TelemetryProfile(system_id, component_id, port, replay_path)` and `TelemetrySupervisor(profile, trust)` provide an installed process lifecycle around the signed decoder. The trusted local caller supplies an already provisioned `SigningTrust` and replay journal. Call `start()` once during service startup, read `snapshot()` optionally, and call `close()` on shutdown. Listening and expiry continue with no viewer, phone, WAN or licensing service. No key is accepted through UDP or an HTTP request. Port0 selects an ephemeral local test port; normal provisioning should choose a fixed loopback port.

The parent starts one child using spawn and a bounded latest-message mailbox. It independently expires status at the original 100ms receipt deadline, including worker stalls/death. Crash recovery waits two seconds, permits at most five retries per minute, and reuses the same grant/journal; it never silently renews authority or creates missing replay state. Key expiry, clock discontinuity and reported journal faults latch failure. A worker without messages for ten seconds is reaped. These are software lifecycle bounds, not physical timing guarantees.

Status contains aggregate state, fixed reason codes, sample count, port, authentication flag, restart count and peak poll duration (milliseconds, capped60000). It never exports the key, journal path, coordinates, orientation values or a trajectory. `perception_eligible` stays false. Additional bounded peaks isolate signed decode (`max_decode_ms`), journal transaction (`max_commit_ms`), and validated message emission-to-parent consumption (`max_delivery_ms`). All peaks are ceiling-rounded wall-clock milliseconds capped at60000; scheduling pauses count toward each interval. Child peaks reset on worker restart; delivery peak spans the supervisor lifetime. No per-packet history is retained or exported. These diagnostics do not extend freshness or prove a hardware latency bound. Finite boot-bound trust is not automatically renewed.

**Current negative evidence:** the installed suite passed35/36 tests; `test_crash_restart_reuses_grant_and_replay_journal` failed to obtain a fresh observation from its periodic stream (peak poll715ms). Earlier single-packet tests expired with peak poll143ms, and a source run missed the10s startup deadline. These failures remain recorded and the test remains enabled. A separate startup probe reached readiness in2.08s, which does not erase the timeout. Clock-read ordering and failed-spawn cleanup regressions have RED→GREEN tests. Timely worker availability is not qualified.

The worker now has an optional `ApplianceConfig`/CLI integration described below. Automatic trusted clock-anchor issuance/renewal, signed Linux image/SDK integration, Linux/SITL lanes and full qualification remain pending. Do not add it to a deployed vehicle/drone on the strength of these development tests.

A subsequent diagnostics checkpoint passed40/40 installed tests (23.114s), with SQLite ResourceWarnings still present in that run. A subsequent connection-cleanup fix passed41/41 installed tests (10.721s) with ResourceWarnings treated as errors and no warnings in the captured log; corrupt-store initialization now closes its connection before rethrowing. The earlier availability failures remain unresolved; new timing counters support attribution on recurrence. See [timing evidence](../../../../docs/engineering/aethron-ecosystem/evidence/phase3/telemetry-timing.json).

## Local credential loader (development)

`aethron_edge.telemetry.provisioning.load_trust(path, system=1, component=1)` reads an existing private credential and returns `SigningTrust` without changing its anchor or deadline. Version1 is a JSON object with exactly `version` (integer1), `boot_id` (canonical lowercase Linux kernel boot UUID), `system_id`, `component_id`, `key_hex` (64 lowercase hexadecimal characters), `link_id`, `timestamp_floor`, `issued_ns` and `valid_until_ns`. Numeric limits follow `SigningTrust`; the sender tuple must match the requested tuple. Timestamps are local monotonic nanoseconds for the named boot, not wall time. Duplicate/extra fields, malformed data, files over2048 bytes, future issuance and expired leases are refused.

The existing file must be a regular single-link file owned by the service UID, mode0600, under a directory owned by that UID with mode0700. The loader pins the directory descriptor, refuses leaf/immediate-parent symlinks and special files, checks descriptor metadata before/after a bounded read, and checks expiry after loading. Same-UID administrators and the ancestor path namespace remain trusted. Provision and rotate credentials through a trusted local administrator/boot service, never HTTP or incoming MAVLink. Keep keys out of signed distributable bundles, Git and logs. A shared-key credential is not TPM attestation or proof of a physical sensor.

`current_boot_id()` obtains the Linux kernel `/proc/sys/kernel/random/boot_id`. Missing/unsupported boot identity fails closed; a random application session ID or a stored UUID is not a substitute. Current Mac tests inject a synthetic kernel identity to test POSIX storage semantics; actual Linux boot-service provisioning and image integration remain pending. There is no automated lease issuance/renewal or reboot re-anchoring in this loader. Those need a separately trusted clock source/policy; never rewrite an expired file or reset the replay journal to make startup succeed. The existing in-memory interface remains available to trusted platform-specific provisioners.

## Appliance configuration and CLI

The administrator-local configuration accepts an optional `telemetry` array (maximum2 entries, unique names and loopback ports). Each entry contains a sender/port, replay journal and exactly one authority source. The legacy credential form is:

```json
{
  "name": "flight",
  "system_id": 1,
  "component_id": 1,
  "port": 14560,
  "credential_file": "/var/lib/aethron/telemetry/flight/credential.json",
  "replay_file": "/var/lib/aethron/telemetry/flight/replay.db"
}
```

Keep the existing camera `profiles`, API credentials and signed bundle settings. Paths are relative to the configuration directory unless absolute. The optional MAVLink SDK must already be installed in the selected edge environment. The trusted local provisioner must supply the current-boot credential and explicitly create the journal once; boot loads existing state. Private credential and mutable journal paths must be outside the distributable signed bundle. Signature verification still covers the configuration containing those references, while private host storage is the credential trust boundary.

`aethron-edge run --config /path/to/appliance.json` loads all telemetry authority before starting sources, then owns the telemetry workers alongside camera processing before HTTP startup. Invalid credentials fail startup with the existing fixed CLI error; it does not recreate state. Each telemetry worker independently handles expiry and bounded crash retry. Aggregate local status adds a `telemetry` map keyed by profile name; telemetry faults contribute to appliance fault state. No measurements, keys or paths are exported, and authentication never promotes telemetry to perception. Shutdown, including HTTP startup failure, closes owned telemetry workers. No network key-management endpoint is added.

This integration is development-tested with real signed localhost UDP traffic and installed consumers on macOS using an injected synthetic Linux boot identity. It does not qualify the Linux appliance image, boot-time credential issuer, physical autopilot, or field timing. Reboot/expiry requires a trusted fresh clock anchor; automatic offline boot issuance remains a separate implementation gate.

## Linux ARM64 software consumer and optional image SDK

`requirements-mavlink-linux-arm64-py312.lock` pins the CPython3.12 glibc>=2.17 ARM64 wheels. The hashes were retrieved2026-10-09 from official [pymavlink metadata](https://pypi.org/pypi/pymavlink/2.4.50/json), [fastcrc metadata](https://pypi.org/pypi/fastcrc/0.5.0/json), and [lxml metadata](https://pypi.org/pypi/lxml/6.1.3/json). Preserve their distribution license notices; the lock does not grant additional redistribution rights.

Populate a dedicated directory containing only the three SDK wheels:

```sh
python -m pip download --only-binary=:all: --implementation cp \
  --python-version 3.12 --abi cp312 --platform manylinux_2_17_aarch64 \
  --require-hashes -r integrations/edge/requirements-mavlink-linux-arm64-py312.lock \
  --dest build/mavlink-linux-wheels
```

The existing `packaging/appliance/image/prepare.py` accepts `--mavlink-dependencies build/mavlink-linux-wheels` alongside `--ros-dependencies`. This is optional and requires the Jazzy/Python3.12 guest. It validates the complete SDK closure before copying, extends the existing offline hash-locked install, records SDK/lock/test hashes in the signed image manifest, and runs `tests/mavlink/linux_runtime.py` in the built image before export. No credentials, journal or enabled telemetry profile are shipped by this option. The operator's signed configuration must reference separately provisioned private state.

Development evidence includes57 installed tests and two additional real Linux kernel-boot/appliance tests in an isolated nonroot ARM64 Python3.12.15 container with networking disabled. These checks used real signed localhost packets, synthetic keys and a temporary current-boot grant. They are not ROS/systemd image, VM reboot/soak, automatic trusted clock issuance, or physical autopilot qualification. The previous locally pinned AETHRON tool/ROS images were absent when inspected; rebuilding and running the complete signed image path remains pending. See [Linux SDK evidence](../../../../docs/engineering/aethron-ecosystem/evidence/phase3/telemetry-linux.json).

## Explicit offline boot-clock authority (development API)

`telemetry.boot_authority.BootClockPolicy` contains the private key, system/component/link tuple, an administrator-approved UTC interval (`not_before_unix_ns`, `not_after_unix_ns`), `lease_ns`, and `drift_budget_ns` (1ms–1s). The interval authorizes use; it does **not** prove that system UTC is correct. A trusted offline clock/provisioner is still required. The default realtime reader is the host system clock, with no RTC accuracy, NTP, TPM or hardware attestation claim.

After explicit replay-journal provisioning, `provision_boot_authority(path, policy)` binds that existing journal to the policy once. It refuses existing authority state and never resets the replay counter. `issue_boot_trust(path, policy)` samples UTC between two local monotonic reads (maximum1ms bracket) under the journal transaction and obtains the Linux kernel boot ID. It returns a `SigningTrust` with `boot_bound=True`; pass this object directly to `SignedTelemetry`/`TelemetrySupervisor`, preserving that flag through process IPC. Do not serialize it into the older version1 credential format, which lacks the explicit binding flag.

The initial signing floor is UTC converted to MAVLink's10µs epoch units. It must exceed committed replay state. The deadline is bounded by both the configured lease and UTC policy end. Repeated calls in the same boot—including a fresh process—reuse the original floor, issue time and deadline. Persisted last-checked clock readings prevent coordinated clock rollback or a subsequent boot going behind the last validated UTC reading. Same-boot drift, rewind, expiry and invalid samples revoke reuse; restoring the clock does not clear that revocation. A new boot needs a fresh valid clock sample above both the stored UTC check and replay counter. No automatic same-boot lease renewal is provided.

The receiver checks the exact persisted grant and revocation state before committing each packet. A missing authority table remains a fault after worker restart when `boot_bound=True`; it cannot fall back to the legacy manual-trust path. Previously cached observations still expire within the existing100ms receipt bound. Grant issuance/validation is not a background clock monitor, and it does not deliver instantaneous revocation to an idle receiver. No payloads, trajectories or keys are written to the journal: only replay/authority metadata, the current boot ID and policy digest. Protect that database from trusted-owner rollback; software alone does not establish power-loss durability or tamper-proof monotonic storage.

Appliance startup can instead use `clock_policy_file` in place of `credential_file` (both or neither are rejected). `load_boot_policy(path, system=1, component=1)` requires the same private file rules and bounded strict JSON as the legacy loader. The policy JSON has exactly `version` (integer1), `system_id`, `component_id`, `key_hex` (64 lowercase hex characters), `link_id`, `not_before_unix_ns`, `not_after_unix_ns`, `lease_ns`, and `drift_budget_ns`. Limits follow `BootClockPolicy`; the configured sender must match. These are a separate policy schema, not v1 boot credentials. The loader does not issue or modify state.

Before enabling this mode, a trusted administrator must provision the replay journal and call `provision_boot_authority(journal, load_boot_policy(...))` once under the service UID. Normal startup loads the private policy, validates its existing journal binding and calls `issue_boot_trust`; a missing journal/binding, replaced policy, unsupported kernel identity or invalid clock fails startup before sources start. Restart never provisions state or renews the grant. Policy/key and journal paths must stay outside signed distributable bundles. No secrets belong in HTTP, command-line arguments, Git or logs. Legacy credential configurations remain supported.

Installed Linux container tests cover both credential and policy startup with real kernel identity and signed loopback packets. Systemd provisioning and safe lease renewal remain pending; the container is not reboot/soak/physical clock qualification. The new path changes neither100ms observation expiry nor `external_unverified`/perception-ineligible semantics.


### Active policy-clock monitoring

Appliance `clock_policy_file` mode passes the loaded policy to the owned telemetry worker. `TelemetrySupervisor(profile, trust, clock_policy=policy)` is the equivalent trusted library entry point; it requires a boot-bound grant and matching key/sender/link. Legacy callers keep their existing interface. The worker's `BootClockGuard` checks the persisted authority before polling and rechecks at50ms intervals while active. It compares the returned grant with the original grant; no renewed/reanchored grant is accepted. Invalid clocks, persisted revocation, expiry and failed checks cause a fixed fault and close the receiver. The running policy is a private in-memory snapshot; changing its file requires an administrator-controlled restart, not hot reload.

An emitted observation's expiry is also capped at100ms from the **start** of the last successful clock check. SQLite latency or worker scheduling cannot extend that authority; the parent independently expires cached status if the worker stalls. The50ms schedule is a polling intention, not a hard real-time guarantee or instantaneous revocation. Existing100ms receive freshness still applies. A clock jump/revocation may leave an already cached observation until its bounded expiry. Focused tests cover delayed validation, rollback, changed grants, real-journal drift revocation and worker expiry propagation; installed Linux testing includes revocation with no further packets or viewers.

Current monitoring persists high-water checks at roughly20Hz using synchronous SQLite transactions. Disk latency, write endurance, flash wear and power-loss behavior require exact-platform measurements; no embedded resource or safety qualification is implied. The clock remains administrator-trusted system UTC. Lease expiry deliberately stops telemetry; safe long-uptime renewal, systemd provisioning and VM reboot/soak remain outstanding.

Readiness diagnostics also expose supervisor-lifetime counts `messages_received`, `observed_messages` and `expired_on_arrival` (saturating at2^31−1). Only validated child messages contribute; these are status-message counts, not distinct sensor samples. `message_state` and `message_age_ms` describe the latest cached status, with `none`/null before any message and age capped60000ms. `max_owner_gap_ms` measures the longest telemetry owner-loop interval, excluding initial grant age. These aggregate diagnostics retain no payload/position history and never grant authentication or extend expiry. A high observed-message count can coexist with an expired current status.

### One-time administrator policy binding

With the private policy file and replay journal already provisioned, run as their owning service UID:

```sh
aethron-edge bind-telemetry-policy --config /etc/aethron/appliance.json --name flight
```

The named telemetry entry must use `clock_policy_file`. Appliance mode verifies its signed configuration first; explicit local interactive mode uses the administrator's local configuration. Successful output is `{"policy_bound":true,"authority_issued":false}`. This operation only binds the policy to an **existing** journal, preserving its counter; it never creates/reset a missing journal, issues a grant, starts workers or renews authority. A second binding fails without overwriting state. First provisioning can use the explicit command below or the trusted `provision_replay` API with the operator's chosen replay floor; never delete an existing journal to make binding succeed. Normal `run` then validates the bound policy and issues/reuses the current boot grant. No key appears in command arguments or output.

### Initial replay and policy provisioning

For a new installation, prepare the private policy and signed appliance configuration,
then run as the service UID (the destination parent must already be owned by that UID
with mode0700). Keep policy, key and journal outside the signed bundle:

```sh
aethron-edge initialize-telemetry --config /etc/aethron/appliance.json --name flight --replay-floor "$ADMINISTRATOR_REPLAY_FLOOR"
```

The replay floor is a required administrator-established MAVLink signing timestamp
(10-microsecond units since2015-01-01 UTC). Do not derive it from an unauthenticated
first packet or lower it to accept old traffic. The command validates the selected
sender and private policy, verifies appliance-mode configuration, stages both replay
and policy tables privately, then publishes with an atomic no-replace hard link.
Output is `{"policy_bound":true,"authority_issued":false,"journal_created":true}`.
The equivalent library API is `initialize_boot_authority(path, policy, timestamp_floor=...)`.
Neither path issues a grant or starts processing. Normal startup still refuses missing
state; this is an explicit one-time administrator operation, never boot-time recovery.

On an installed Linux appliance with its existing nonroot `aethron` account,
the administrator can run the repository's installer in explicit provisioning mode:

```sh
sudo python3 packaging/appliance/install.py --initialize-telemetry flight --replay-floor "$ADMINISTRATOR_REPLAY_FLOOR"
```

This uses only `/opt/aethron/venv/bin/python` and `/opt/aethron/appliance.json`.
It drops to the account's UID/GID, clears supplementary groups and inherited
environment, uses an isolated interpreter and private umask, and discards child
output. It does not start/restart the service, create accounts, copy keys, change
existing permissions or retry on error. A timeout may follow publication; preserve
state for inspection. The installed executable tree/configuration and account
database must be administrator-owned and trusted. Provision the private policy
under that service UID before invoking it. The service declares
`StateDirectoryMode=0700`; image recipes also create `/var/lib/aethron` with that
mode. Generic installer users must prepare that directory and account explicitly
before first provisioning. No provisioning command is added to boot services or the
ROS SDK installer. The SDK installer only establishes pinned library paths.

Any existing destination, including a dangling symlink or partial file, is refused.
The parent and its ancestor namespace must remain administrator-trusted. Runtime
requires a private single-link journal. An abrupt process/power interruption can leave
private staging residue, or a published two-link journal that runtime rejects. A failure
after publication (including directory sync failure) can leave a complete journal even
though the command reports failure. Preserve that state for administrator inspection;
never delete/reset it or lower its replay counter to retry. Filesystem power-loss,
flash endurance, Windows support and automated systemd provisioning are unqualified.

The live telemetry supervisor waits on its own child's process-exit sentinel with the existing10ms timeout. It uses [Python's documented process-sentinel wait](https://docs.python.org/3.13/library/multiprocessing.html#multiprocessing.connection.wait), without changing OS priority or freshness bounds. Snapshots also check the exit sentinel with zero timeout before reporting authentication, so an already exited child cannot authorize cached status through a stale liveness result. When no child exists during backoff, the existing stop-event wait remains. In one Mac launch environment, condition timers overshot while descriptor polling was substantially closer to its requested interval; this is an environment-specific observation, not a real-time guarantee.

To reproduce the bounded scheduling comparison using an installed SDK-enabled environment:

```sh
python -I -B tests/mavlink/scheduling_probe.py --fixture "$PWD/examples/temporal-blackout.jsonl"
```

The probe runs three eight-second windows (telemetry alone, with replay-camera processing, alone again), using an independent synthetic loopback sender. It reports CPU time, wall gaps and aggregate statuses, retains no sensor payload history and cleans up its own children. It intentionally preserves sender/reader waits to reveal their scheduling delays; it is diagnostic evidence, not a qualification gate. Camera computation was small relative to the observed pauses in the recorded run; the exact host-policy cause and reliable Mac readiness remain unqualified. See [scheduling evidence](../../../../docs/engineering/aethron-ecosystem/evidence/phase3/scheduling.json).

### Optional signed-image SIL boot check

The image builder's explicit `--mavlink-dependencies` lane now stages a separate
signed `telemetry-appliance.json` and a service-UID oneshot boot check. Image
construction invokes the installed initialization CLI once, storing a **public
synthetic test key**, policy and replay journal outside the signed bundle in
`/var/lib/aethron-telemetry`. This fixture uses floor0, a broad test UTC window,
a60s grant and the unchanged1ms clock-sample/drift bounds. These are test fixtures,
not a deployment key or an attestation of UTC. Never reuse this SIL image/key for
real telemetry trust. Ordinary images without the optional SDK lane do not enable
this check; the normal application service gains no initialization hook.

At boot, `aethron-telemetry-check.service` reads existing state, validates signed
configuration, issues/reuses the kernel-bound grant, injects one synthetic signed
packet through the installed SDK receiver and verifies duplicate rejection and
counter advancement. It never provisions or resets on boot. Same-boot calls must
preserve the original grant; expiry still refuses further checks. Its current-boot
result is required by the aggregate SIL probe. This covers direct SDK ingestion,
not UDP, supervisor continuity or hardware. Actual systemd VM boot/reboot and the
new image's full qualification remain pending; offline container and assembly
checks alone do not satisfy those gates.
