# AETHRON edge candidate — developer and maintenance use

Normal installed appliances boot automatically; see [appliance operation](usage-appliance.md). The commands here are developer/service tools. The candidate has no public package release or hardware qualification.

Use CPython 3.11 or newer (3.13.15 was executed here) in a project-local virtual environment. On Unix, activate with `. .venv/bin/activate`; on Windows use `.venv\Scripts\Activate.ps1`. These explicit setup steps may download build tools/dependencies; steady-state runtime does not require the network.

```sh
python -m venv .venv
# Activate the environment using the command for your OS before continuing.
python -m pip install build==1.6.1 setuptools==84.0.0 wheel==0.48.0
python -m pip download --require-hashes -r integrations/edge/requirements-server.lock -d build/ecosystem-phase1/wheelhouse
python scripts/edge_package_check.py
python -m pip install --no-index --find-links build/ecosystem-phase1/wheelhouse --require-hashes -r integrations/edge/requirements-server.lock
python -m pip install --no-index --find-links build/ecosystem-phase1/package/a 'aethron-edge[server]==0.1.0'
aethron-edge doctor --config examples/edge-replay.json
aethron-edge replay --config examples/edge-replay.json
```

The package check builds both wheels twice and executes an isolated installed HTTP/SSE consumer outside the checkout. It fails on unequal builds or a nonworking consumer. The locked server/client closure includes HTTPX for the Python observation example; the base wheel alone is sufficient for import/doctor/replay but does not install every optional client/vision dependency.

For the actual pixel paths, explicitly download/install `integrations/edge/requirements-vision.lock` with `--require-hashes` and fetch the pinned test model using `python scripts/fetch_rgb_model.py`. To run the test RTSP server, install test-only `imageio-ffmpeg==0.6.0` and run `python scripts/edge_fetch_test_tools.py`. Then `python scripts/edge_pixel_service_e2e.py` exercises installed file and RTSP inference/service/client paths. No runtime command fetches model weights automatically.

`doctor` opens no sensor, downloads no model and makes no qualification claim. Replay produces a bounded, explicitly labeled report. For a local service, provision a 32-byte random hex token in an owner-only file and configure named profiles, credentials and a local status file. `aethron_edge.runtime.provisioning.create_token(Path(...))` creates the token without printing it. Example configuration:

```json
{"version":1,"runtime_mode":"interactive","host":"127.0.0.1","port":8765,"profiles":[{"name":"bench","driver":"replay","address":"temporal-blackout.jsonl","contract":"warn"}],"credentials":[{"token_file":"token","principal":{"name":"owner","scopes":["observe","session:manage"]}}],"status_file":"status.json"}
```

Addresses are resolved relative to the configuration. Start `aethron-edge serve --config local.json`, then `python examples/clients/observe.py --token-file token --profile bench --limit 3`. `scripts/edge_package_check.py` exercises this from a fresh installed environment outside the checkout. Never put credentials in query strings or camera URLs in public logs.

File/RTSP profiles select `ffmpeg`; UVC profiles select the actual OS backend (`v4l2`, `avfoundation`, `msmf`) and an authorized device index. Pixel profiles require an explicit local pinned YOLOX model, lighting domain and optional vision dependencies. Generic OpenCV does not establish exposure timing: real decoding/inference runs, but current v3 evidence remains UNKNOWN when timing is unqualified. File and local RTSP tests are software evidence; virtual UVC tests do not qualify physical cameras. RGB is ineligible outside daylight under v3.

The API accepts only configured source-profile names. It has no arbitrary URL/file/model/command endpoint. Default loopback still requires authentication; cross-origin requests and token URLs are rejected. Remote binding is deliberately not exposed in this candidate: a separately configured authenticated TLS proxy can consume the protected local interface after its deployment is reviewed. No plaintext LAN listener is silently enabled.

GPL-3.0-only community licensing and separately negotiated commercial terms apply to project-owned code. Models, datasets and dependencies retain their own licenses. No online license heartbeat is required.

For explicit offline pixel evaluation, `aethron_edge.pixel_replay.replay_images(image_paths, model_path)` decodes each supplied licensed image, runs the pinned detector, estimates background registration and returns a strict replay report through the unchanged core. Its clock and identity registration are explicitly virtual; it cannot qualify exposure latency or a physical rig. No annotations are supplied to inference.
