# Threat model — planned integration boundaries

Scope: source drivers/decoders, core boundary, service, clients, packages and operator configuration. This is a design analysis, not a completed penetration test. Assets are truthful current perception, bounded resources, source/model integrity, user privacy and separation from vehicle control. Adversaries include malicious network peers, corrupted camera firmware/streams, hostile web pages, compromised plugins/packages and unauthorized local users. Model insufficiency and clock faults can produce harm without an adversary.

| Threat / boundary | Required mitigation | Concrete negative check |
|---|---|---|
| Forged timestamps, replay, frozen camera frame | Exposure clock mapping with bounded error; trusted now; sequence/clock reset; calibrated stale rejection | Replay old frame with new receive time; result not fresh |
| Decoder exploit/decompression bomb | Separate low-privilege process, size/dimension/time caps before allocation, pinned decoder build | Truncated codec stream/huge dimensions/timeout; worker restart and UNKNOWN |
| Plugin code execution | Admin-installed digest allowlist, separate packages/permissions, no arbitrary module path/entry-point auto-load | Unknown plugin/disallowed permissions cannot start |
| RTSP SSRF/credential leak | Local config allowlist, fixed destinations/schemes, no user-supplied URL endpoint, redacted logs | API URL injection and redirect-to-local-service blocked |
| Remote API/session abuse | Loopback+token default, scopes, ownership checks, TLS for remote, rate/session caps | Wrong token/principal/Host/Origin rejected without payload echo |
| Browser DNS rebinding/CSRF | Host/Origin allowlist, default no CORS; authenticated fetch SSE | Hostile Origin cannot create/read a session |
| Slow subscriber/resource exhaustion | Latest-only queues, bytes/RSS limits, worker quotas, read/send timeouts | Flood/stalled client does not grow history; closes with UNKNOWN |
| Ground truth leaking into inference | Separate inference/evaluation APIs/processes, immutable data split/model digests | Detector cannot open labels; run without label mount and compare output |
| Model tampering or unintended provider fallback | Explicit fetch/signature/hash, provider requirement, output validation | Wrong digest/provider/shape fails closed |
| False tracking/identity misuse | Geometry only, bounded scene lifetime, no external track IDs/embeddings, deletion on reset | Forbidden fields, cross-camera keys and expired IDs rejected/unlinked |
| Observations accidentally trigger control | No command endpoint/plugin permission; separate process/network capability | Instrument outbound traffic in SITL; no arm/mode/actuator messages |
| Supply chain/update rollback attacks | Signed manifest, hash locks, SBOM/license audit, minimum safe version policy | Tampered/expired/incompatible update refused; known-good rollback tested |
| Privacy leak through logs/crash reports | No raw images, boxes/IDs/routes or credentials in persistent telemetry by default | Fuzz sentinel private text; absent from output/logs/errors |
| Stale UI after disconnect/suspend | Local monotonic expiry; clear on foreground/resume/reconnect until fresh evidence | Suspend app/stop service; no persistent current box |
| Physical remount/tampering | Calibration identity/expiry and installation inspection | Change resolution/mount record; refuse old calibration |

## Trust partitions

Raw images and source URLs are untrusted input; model outputs are untrusted proposals, not truth. The core validates finite geometry/time and applies frozen rules. Authenticated clients are not entitled to set trusted time or hardware qualification. Administrators may configure authorized devices but cannot disable the safety floor. Vendors/SDKs are not automatically trusted for clock or calibration accuracy. Network boundaries do not make JSON harmless: reject duplicate keys, nonfinite values and excessive depth before schema coercion.

No biometric identity, appearance embeddings, durable person IDs, location stitching, long-term person history, threat score, target designation, pursuit or weapons. The v2 through-obstruction channel remains coarse. Prohibited data must not enter a plugin manifest, SDK extension or audit log as an “optional” escape hatch.

## Security verification and residual risk

Run repository static policy and both fuzzers, then adapter parser/codec fuzz with CPU/memory/time caps and no external network. Test API authentication/session isolation, pinned dependency audit, secret scan, license/SBOM/provenance and installed updates. Existing Bandit results cover only inspected Python; they are not decoder/vendored SDK/OS assurance. Zero findings is not an independent audit. Hardware supply chain, adversarial physical scenes, compromised operating system, dataset poisoning and certified controller behavior remain outside Phase 1 assurance; document their residual impact per deployment before Level D.

## Unattended-appliance additions

Threats include malicious provisioning, stolen local device keys, unsigned/rollback updates, startup dependency on unavailable cloud, unbounded crash loops, disk wear/full storage, hostile local clients stopping inference and a dead process with a falsely reassuring indicator. Require authenticated commissioning, protected local admin identity, offline integrity verification, atomic signed updates, bounded restart/storage, supervisor-owned pipelines and independent fault indication. Test loss of every optional client/backend and cold boot with WAN unavailable. Hardware watchdog/indicator assurance remains a per-SKU gate. Persistent administration keys must never become persistent person/scene identity.

## Phase 1 implemented controls and reviewed limits

Actual evidence is in [security review](evidence/phase1/security-review.json), [checkpoint checks](evidence/phase1/checkpoint-checks.json) and [retained counterexamples](evidence/phase1/negative-checkpoints.json). The review is single-author, not independent assurance. Four low-severity Bandit findings remain explicitly reviewed around fixed-argument OpenSSL and verified-slot exec; no known vulnerabilities were reported for the locked dependency closure on the check date. Neither result audits the kernel, codecs or hardware.

The API is authenticated loopback only, with strict body bounds, ownership/scopes, denied Origin/Host/query misuse, four viewer handles and eight streaming subscribers. Source configuration and model paths are local admin inputs, never network-selected commands. Actual codec workers suppress native URL diagnostics; no raw images or scene IDs enter persistent status. Windows job-object code follows [S65](SOURCES.md#s65)/[S66](SOURCES.md#s66), but its native execution remains pending.

A reproduced filesystem counterexample showed that a root-owned update directory inside a service-writable parent can still be renamed by that service account. The corrected appliance uses root-owned `/var/lib/aethron-updates` beneath root-owned `/var/lib`, outside the status directory and outside service write paths. The installer activates signed slots separately; startup only reads/verifies/execs them. The native Linux negative permission test denies store replacement, and the selected verified runtime still processes. Root trust replacement, hardware-backed anti-rollback and secure boot remain separate qualification requirements.

Decoded-size checks and one-slot buffering do not prove every native codec allocation is bounded. The Linux service has a 768MiB cgroup limit; other native OS/resource cells require execution before support claims. Generic OpenCV streams do not provide qualified exposure timestamps. Software render-time/client expiry and no-current-support UNKNOWN remain mandatory even when processing is slow or unavailable.
