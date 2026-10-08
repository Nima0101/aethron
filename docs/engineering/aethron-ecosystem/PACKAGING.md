# Packaging and installation plan

## Current versus proposed

Existing `pyproject.toml`: AETHRON **0.2.0**, Python **>=3.9**, zero core runtime dependencies, setuptools **84.0.0**, wheel **0.48.0**; existing optional vision NumPy **2.3.5**, OpenCV headless **4.13.0.92** requires a newer Python environment. Optional Core ML dependency file pins ONNX Runtime **1.30.0**. Preserve these until a separately tested migration. Local source/wheel availability is not proof that a public index package is controlled or installed by users.

Proposed `integrations/edge/pyproject.toml`: distribution `aethron-edge`, import `aethron_edge`, console entry `aethron-edge`, version **0.1.0**, Python **>=3.11**. It depends on the tested core version, with optional `server`, `uvc`, `rtsp` extras; install the exact release through a signed lock/wheelhouse. Existing core installation remains lightweight and offline. Never force ROS, vendor SDKs, GPU libraries or server packages on all users.

## Distribution matrix

| Artifact | Initial build/consumer target | Qualification limits |
|---|---|---|
| Core pure Python wheel + sdist + zipapp | Linux/macOS/Windows; CPython 3.9 and 3.13 current evidence lanes | OS execution evidence separate from portability intention |
| Edge Python wheel | CPython 3.11/3.13; Linux x86_64/arm64, macOS arm64/x86_64, Windows x86_64 | Camera backend availability checked per OS; Windows arm64 initially experimental |
| OCI CPU image | Linux amd64/arm64, explicit per-arch manifest digests | Docker on macOS/Windows runs Linux VM; native camera passthrough not implied |
| Jetson image | Exact L4T/JetPack/CUDA/provider tuple | Cannot reuse arbitrary desktop CUDA base; pinned vendor EULA/runtime inventory |
| ROS package/container | Ubuntu 22.04/Humble/PX4 lane; separate Ubuntu 24.04/Jazzy image lane | Do not mix distro ABIs or firmware messages |
| Swift/Kotlin SDK | transport fixture package initially | Separate native owner builds; no Phase 0 native modifications |
| TypeScript SDK | generated types plus fetch/SSE wrapper | Contract tests against installed service, browser origin policy |
| C++ API | JSON consumer first; stable C ABI later if embedded demand | No ABI promise until compiler/arch/ownership tests |

## Practical install flow to implement

Download a release manifest; verify signature, digest and expected publisher. Create a per-project virtual environment. Install pinned wheels offline from `wheelhouse/`; run `doctor` and recorded replay before granting device access. Explicitly fetch separately licensed model artifacts and verify hashes; runtime never downloads weights. Configure one authorized source/profile and calibration. Start the local service under the ordinary user, then run the installed sample consumer. Validate disconnect/UNKNOWN and version report before any hardware claim. Upgrade by building a fresh environment, checking migration/rollback, then switching a launcher pointer atomically.

Proposed container command after a real release:

```sh
# SPEC ONLY: release digest and profile must come from verified artifact manifest
podman run --rm --read-only --cap-drop=ALL --security-opt=no-new-privileges   --network=none --mount type=bind,src=./fixtures,dst=/fixtures,ro   aethron-edge@sha256:RELEASE_DIGEST replay --config /fixtures/edge-replay.json
```

For a device profile, grant only the selected device node and necessary group, not `--privileged` or all of `/dev`. For RTSP, explicitly permit the configured camera network and deny arbitrary egress. Rootless camera/GPU access varies by runtime/host: test the actual combination and document limits. Container command intentionally contains a named placeholder, not a fake digest.

## Release chain and licensing

Source archive, wheel, sdist, zipapp and OCI images need checksums, dependency/model/data SBOMs, license notices and provenance bound to source SHA. Verify two builds where reproducibility is claimed; native/GPU nondeterminism must be reported, not suppressed. Registry names/package ownership are unresolved until verified under owner authorization. Use trusted publishing/OIDC only in a separately approved release workflow; Phase 0 workflow has read-only permissions and no publication job.

Apache source does not license third-party weights, datasets, video codecs, firmware or vendor SDK redistribution. Keep proprietary adapters in optional packages installed by the authorized user; review GPL/LGPL/AGPL and patent obligations per actual build. GStreamer/FFmpeg plugin selection changes licensing. Do not redistribute SDK archives under the core license. No `curl | sh`, unauthenticated model URL, floating `latest` tag or fallback extra package index in released recipes.

Semver tracks public Python/API stability; model changes also require evidence-version changes even if function signatures match. During 0.x, announce breaking minor releases and provide one prior tested contract adapter; do not mutate frozen protocol v3. Support lifetime/security fixes are release policy commitments to establish before 1.0, not promises made by this plan.

## Primary normal-user packaging: installed appliance

[APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md) is the mandatory packaging/lifecycle specification. Wheels, CLI and `podman run` examples above are developer and maintenance interfaces. Normal vehicle/drone/home users receive a signed preinstalled image/native package or guided one-time installer that enables the OS/vendor boot supervisor. They power on the fixed device; capture/inference/local status start without login, terminal, provisioning laptop, phone, WAN, Supabase, Coolify or license heartbeat.

Initial implementation artifacts: Linux amd64/arm64 edge image candidate and installable service package with systemd unit, local model/plugin/config manifests, dedicated account, bounded restart/logging, local notifier/API and offline update/recovery utility. Model/SDK terms must permit offline startup; incompatible activation requirements block that plugin's standalone classification. OEM integration uses its approved signed-package/service mechanism; Windows/macOS install targets must prove camera permission and unattended-session behavior before that label. A launch-at-login desktop preview is a separate useful mode, not a substitute for the appliance gate.

Stage signed updates atomically in inactive slots/versioned directories, test migration and rollback against offline corruption/power-loss cases, and provide secure local factory reset/reprovisioning. P1.7 creates the real service-manager VM acceptance harness and image; no image/package/service file is created in Phase 0. [Home camera/hub guide](HOME-CAMERA-COMPATIBILITY.md) supplies the fixed LAN/PoE recipe. Keep local sensor buses and protected power connected during the no-companion/WAN test.
