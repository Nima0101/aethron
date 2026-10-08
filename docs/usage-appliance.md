# Installed AETHRON appliance candidate

The Linux appliance starts a supervisor-owned local pipeline at boot. Once provisioned, it needs local compute, sensors and power; it does not need a phone, laptop, user login, WAN, account or licensing server. Optional HTTP clients only observe. Closing a client does not stop processing.

This is a **software candidate**, not a qualified vehicle, drone or zero-visible-light product. The boot test uses synthetic multimodal proposals. Real file/RTSP decode and pinned RGB inference have separate tests. Generic OpenCV sources lack a qualified exposure clock and therefore cannot supply current safety evidence. RGB alone cannot see in zero visible light.

## Build and exercise the actual boot image

Run from this checkout using the project-local Python environment and Docker. The commands create local artifacts only. Budget approximately 3 GB disk headroom and over an hour for the soak. Nothing installs a service on the build host. The builder refuses to overwrite an existing boot image so negative evidence survives.

```sh
python scripts/edge_package_check.py
mkdir -p build/ecosystem-phase1
umask 077
openssl genpkey -algorithm ED25519 -out build/ecosystem-phase1/test-only-signing.pem
python packaging/appliance/image/prepare.py \
  --out build/ecosystem-phase1/boot-candidate \
  --wheels build/ecosystem-phase1/package/a \
  --test-key build/ecosystem-phase1/test-only-signing.pem
python scripts/appliance_boot_e2e.py --image build/ecosystem-phase1/boot-candidate
```

Install the hash-locked dependencies and build tools first as described in [edge usage](usage-edge.md). A developer may reuse an already verified local tool image with `--tool-image aethron-phase1-vm-tools:local`; the exact Docker image ID, package inventory and template/wheel hashes are retained. Debian top-level packages and base digest are pinned. The full resolved OS inventory is evidence, not a promise of byte-identical OS images: filesystem UUID/timestamps and package repositories require an archived build environment for that stronger claim. The Python wheels have a separate two-build byte-equality gate.

The builder signs both the runtime bundle and the kernel/initrd/root-filesystem manifest with the supplied **test-only** key. The VM harness verifies that manifest before boot. No private signing key is copied into the image. These local test keys are not production trust roots or secure-boot certification. Protect a future release key separately. Root/admin replacement of the test trust root is outside this SIL threat boundary.

The guest has no virtual NIC, shared guest directory, forwarded port, SSH or login session. systemd enables `aethron.service` under a dedicated `aethron` account. The guest-local test probe observes aggregate status on serial, reboots once, kills an inference worker and runs a one-hour second-boot soak. The probe is test instrumentation, not a user provisioning dependency. This test image deliberately reboots once and powers off after its test; it is not the normal deployment image. The root-directory installer enables only `aethron.service`, so a normal target image must omit the SIL probe service. `result.json`, `serial.log`, `image-manifest.json` and `dpkg.txt` provide evidence. Boot mutates the filesystem; prepare a fresh image for another signed boot run.

## One-time installation and normal use

For a target Linux image, the root-directory installer accepts an explicitly signed complete bundle:

```sh
python packaging/appliance/install.py --root build/target-root \
  --bundle build/verified-bundle --trust-root build/release-trust.pub
```

It verifies before and after copying and enables the boot unit. The image/package integration must create the dedicated `aethron` account, writable `/var/lib/aethron`, and root-owned `/var/lib/aethron-updates` (group `aethron`, mode 0750) under a root-owned parent; the provided image builder does this. This offline root-directory tool does not silently alter the Mac, create foreign user accounts, start services or qualify arbitrary devices. The signed bundle must contain the runtime at `/opt/aethron/venv`, `appliance.json`, fixed source profiles and every required local model/fixture. Select only authorized devices and narrowly required OS device groups. Never grant access to factory camera buses merely because a connector fits.

At power-on the pipeline starts without a viewer. Local `/var/lib/aethron/status.json` is a bounded atomic informational status record with an expiry, aggregate processing/drop counters and no images or track IDs. Drop diagnostics distinguish capture sequence gaps, overwritten pending messages and busy-mailbox rejections; unpublished capture counts at abrupt death may remain unknown. A stale/missing status means unavailable, never SAFE. Monotonic timestamps are boot-local: a reader must also reject future `emitted_ms` values after reboot, and require `emitted_ms <= now_ms <= status_expires_ms`. The candidate provides this local software notifier; physical LED/audio/display wiring and independent process-death indication require per-device integration and qualification. `running` means the supervisor is running, not that perception is qualified. No frames or tracks survive reboot.

Provision local API credentials with the library `runtime.provisioning.create_token`; store them with owner-only permissions. The API binds loopback. An explicitly administered TLS relay can serve a remote viewer; this candidate does not enable remote unauthenticated binding. Source profiles cannot be supplied through HTTP. Local camera RTSP credentials belong in restricted configuration, never public logs or URL query bearer tokens.

## Offline maintenance and recovery

`runtime.updates.UpdateStore` verifies Ed25519 manifests, stages an inactive version directory, re-verifies copied bytes, fsyncs and atomically replaces its active record. `recover()` verifies the active slot; corruption produces `fault`. Earlier versions below the active minimum are rejected. Incomplete staging never overwrites the active slot. `factory_reset()` is a local admin operation; also rotate/remove provisioning credentials with the provisioning module and recommission sensors before use.

The version-directory update API is callable by an authorized offline installer. The boot unit passes `--update-store /var/lib/aethron-updates`: startup verifies the initial bootstrap, verifies the selected slot and execs that slot’s Python/runtime/config. Activation takes effect at the next controlled service restart; it never replaces executing code in place. The signed config uses `integrity_bundle: "."`, and local file/model inputs must belong to the signed bundle. The VM stages an actual second runtime offline, rejects rollback, restarts the service and checks that the selected executable resumes processing. Preserve execute permissions and restrict `/var/lib/aethron-updates` and its slots to root ownership with read/execute access for the `aethron` group. Its parent `/var/lib` is root-owned. Keep the store outside the service-writable status directory: otherwise a compromised service account could rename the whole store and replace its minimum-version record. The systemd unit reads updates through `ProtectSystem=strict`; a separate privileged offline installer stages/activates them. Production A/B OS switching, secure boot, hardware-backed anti-rollback, revocation distribution and OEM update frameworks remain later platform work; do not advertise those as already deployed.

Missing sensors, invalid time, invalid calibration or model failure withdraw current evidence. The supervisor makes at most five restart attempts in 60 seconds, then latches a fault. Service-manager restarts have a separate five/60-second limit. Maintenance may resolve the cause and restart explicitly; no fault authorizes hardware movement. Preserve diagnostic evidence before resetting.

Read the relevant normal-user recipe: [OEM embedded](appliance/oem-embedded.md), [vehicle retrofit](appliance/vehicle-retrofit.md), [drone companion](appliance/drone-companion.md), [home hub](appliance/home-hub.md). Exact hardware power, thermal, mounting, zero-visible sensing and field safety gates remain unqualified.
