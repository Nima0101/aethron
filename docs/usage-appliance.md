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

The guest has no virtual NIC, shared guest directory, forwarded port, SSH or login session. systemd enables `aethron.service` under a dedicated `aethron` account. The guest-local test probe observes aggregate status on serial, reboots once, kills an inference worker and runs a one-hour second-boot soak. The probe is test instrumentation, not a user provisioning dependency. This test image deliberately reboots once and powers off after its test; it is not the normal deployment image. The root-directory installer enables only `aethron.service`, so a normal target image must omit the SIL probe service. `image-manifest.json` and `dpkg.txt` describe the signed base. Each boot invocation creates `runs/<unique-id>/` containing `request.json`, `result.json`, `serial.log` and a writable `rootfs.qcow2` overlay. The base is mounted read-only and its hashes are checked again after the run. Existing run directories are refused; failed overlays and logs are retained. A new run can reuse the unchanged signed base, but changed source/dependencies require a newly built image. Use `--out <fresh-directory>` to select an explicit run directory, or `--inspect --out <retained-run>` to re-evaluate it against the verified base. Old pre-overlay images mutated by boot still fail integrity verification and must not be reused as pristine bases.

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

Signature verification uses a private temporary copy of the exact manifest bytes parsed by the verifier and a bounded 64-byte Ed25519 signature. This avoids authenticating a replacement manifest reopened from the incoming bundle. A writable local temporary directory is required; the supplied systemd units use `PrivateTmp=true`. Copies are removed on success, rejection and timeout. [OpenSSL Ed25519 verification requires input of known size](https://docs.openssl.org/3.5/man1/openssl-pkeyutl/#ed25519-and-ed448-algorithms), so the verifier uses regular temporary files rather than a pipe. Manifest, signature, state and digest reads also check the opened descriptor against the inspected regular file and size. POSIX opens use no-follow and nonblocking flags to reject substituted links/FIFOs before reading. These checks do not make the whole bundle immutable: keep staged/installed files and the trust root administrator-owned as described below. Windows descriptor behavior still needs its platform test lane.

Store mutations (staging, activation and factory reset) use a nonblocking OS lock. An overlapping caller receives `ValueError("update_store_busy")` and must retry the entire operation after the other installer finishes. The empty `.mutation.lock` file remains in place across reset/restart; never delete it to clear contention. Process exit releases the OS lock. Recovery is read-only and does not create or acquire this mutation lock. These guarantees require a local filesystem with functioning OS locks and an administrator-owned store; they are not distributed-filesystem or hardware anti-rollback qualification. The implementation uses [POSIX flock](https://docs.python.org/3/library/fcntl.html#fcntl.flock) or [Windows byte-range locking](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking); Windows execution remains a separate pending qualification gate.

The version-directory update API is callable by an authorized offline installer. The boot unit passes `--update-store /var/lib/aethron-updates`: startup verifies the initial bootstrap, verifies the selected slot and execs that slot’s Python/runtime/config. Activation takes effect at the next controlled service restart; it never replaces executing code in place. The signed config uses `integrity_bundle: "."`, and local file/model inputs must belong to the signed bundle. The VM stages an actual second runtime offline, rejects rollback, restarts the service and checks that the selected executable resumes processing. Preserve execute permissions and restrict `/var/lib/aethron-updates` and its slots to root ownership with read/execute access for the `aethron` group. Its parent `/var/lib` is root-owned. Keep the store outside the service-writable status directory: otherwise a compromised service account could rename the whole store and replace its minimum-version record. The systemd unit reads updates through `ProtectSystem=strict`; a separate privileged offline installer stages/activates them. Production A/B OS switching, secure boot, hardware-backed anti-rollback, revocation distribution and OEM update frameworks remain later platform work; do not advertise those as already deployed.

Missing sensors, invalid time, invalid calibration or model failure withdraw current evidence. The supervisor makes at most five restart attempts in 60 seconds, then latches a fault. Service-manager restarts have a separate five/60-second limit. Maintenance may resolve the cause and restart explicitly; no fault authorizes hardware movement. Preserve diagnostic evidence before resetting.

Read the relevant normal-user recipe: [OEM embedded](appliance/oem-embedded.md), [vehicle retrofit](appliance/vehicle-retrofit.md), [drone companion](appliance/drone-companion.md), [home hub](appliance/home-hub.md). Exact hardware power, thermal, mounting, zero-visible sensing and field safety gates remain unqualified.

The current SIL guest also provisions the bundled synthetic raw-depth recording. Its recording and calibration manifest are signed with the runtime bundle; the image manifest declares `raw-depth` as required recorded evidence. Boot acceptance now requires raw batches on both boots, fresh activity at the end, raw-worker recovery and processing in the updated runtime. Proposal counters cannot satisfy that requirement. Missing/stale samples and faults remain reported. This harness extension has [focused and installed-runtime checks](engineering/aethron-ecosystem/evidence/phase2/raw-boot-harness.json); a new image boot/reboot/one-hour soak is still pending, and older proposal-only results do not qualify it. ROS guest lifecycle checks have a separate assembly path below; boot qualification remains pending.


For the pinned Jazzy ARM64 image, provision its Python 3.12 venv before signing the runtime bundle: run that venv's interpreter on `packaging/appliance/image/provision_ros_sdk.py`. It installs a fixed, non-executable `.pth` path for the image-owned SDK, so isolated Python (`-I`) and spawned workers can import ROS without `PYTHONPATH`. It refuses global Python, unsupported Python versions, writable/untrusted SDK directories and conflicting path files. The SDK itself is supplied by the pinned image, not downloaded by this helper. Its signed `venv/ros.env` contains fixed SDK loader/discovery settings consumed by the ROS guest units. The default Debian/Python 3.13 guest remains separate from the Jazzy/Python 3.12 guest.

`ros_lifecycle_probe.py --config <signed-isolated-ROS-fixture-config>` is guest-only SIL instrumentation. It starts the actual installed signed CLI with an analytical depth publisher and no viewers, then verifies source expiry, rejection after reconnect, explicit restart, source-timestamp rewind and rejection after timestamp restoration. It never changes the OS clock or publishes actuator messages. The fixture requires the four-second synthetic renewal configuration and unchanged 1ms drift budget; unexpected faults fail the run. This path is now in the offline installed ROS check. It is not a real sensor, sustained-availability result or boot/soak qualification.

Build the ROS SIL variant with the same `prepare.py` arguments above plus
`--ros-dependencies <offline-CP312-ARM64-wheelhouse>`. Populate that wheelhouse
from `integrations/edge/ros2/requirements.lock`; installation verifies its pinned
hashes, including the pip bootstrap before execution. Pip is removed after dependency installation and before signing: the installed appliance and its version-directory updater do not need this build tool. Before image export, the builder runs isolated installed-consumer checks for SDK/runtime imports, pip absence, and full signature/file verification of both initial and update bundles. The image manifest records that test source hash. The ROS base is pinned by
digest; Ubuntu systemd and the separately inventoried Debian kernel/initrd supply
the VM boot environment. Image assembly requires package access; boot requires no
network. This is an emulated test image, not an OEM or physical-device image.

Its boot-triggered `aethron-ros-check.service` starts/stops the fixed
`aethron-ros-fixture.service` under systemd and runs the same signed lifecycle
scenario. Raw/proposal processing uses the independent `aethron.service` and its
own configuration, port and status file. The image manifest requires ROS lifecycle
evidence on both boots, bound to distinct kernel boot IDs. Missing or stale ROS
results cannot borrow raw-processing success. Synthetic loss deliberately ends in
a latched fault; the lifecycle check never claims continuous ROS availability.

The assembled image passed the offline installed CLI scenario, but a diagnostic
emulated systemd attempt failed the unchanged 15-second initial status deadline
with no accepted status sample. The cause remains under investigation; no boot,
reboot or one-hour ROS qualification is claimed. See the
[assembly evidence](engineering/aethron-ecosystem/evidence/phase2/ros-assembly.json).

The [pip-free runtime check](engineering/aethron-ecosystem/evidence/phase2/ros-runtime-minimal.json) reduced signed files from 2,270 to 1,385 and passed installed-consumer/lifecycle checks. Its fresh VM run still missed the initial status deadline; the base remained unchanged. Import/schema work and unfinished bundle verification remain startup profiling targets. This footprint improvement is not a boot qualification.
