# AETHRON edge candidate — developer and maintenance use

Normal installed appliances boot automatically; see [appliance operation](usage-appliance.md). The commands here are developer/service tools. The candidate has no public package release or hardware qualification.

Build both local wheels using pinned repository build dependencies. Resolve the hash-locked server dependencies into a platform-specific wheelhouse, then install offline in a new environment:

```sh
python -m pip install --no-index --find-links wheelhouse --require-hashes -r integrations/edge/requirements-server.lock
python -m pip install --no-index --find-links wheelhouse 'aethron-edge[server]==0.1.0'
aethron-edge doctor --config examples/edge-replay.json
aethron-edge replay --config examples/edge-replay.json
```

`doctor` opens no sensor, downloads no model and makes no qualification claim. Replay produces a bounded, explicitly labeled report. For a local service, provision a 32-byte random hex token in an owner-only file and configure named profiles, credentials and a local status file. `aethron_edge.runtime.provisioning.create_token(Path(...))` creates the token without printing it. Example configuration:

```json
{"version":1,"runtime_mode":"interactive","host":"127.0.0.1","port":8765,"profiles":[{"name":"bench","driver":"replay","address":"temporal-blackout.jsonl","contract":"warn"}],"credentials":[{"token_file":"token","principal":{"name":"owner","scopes":["observe","session:manage"]}}],"status_file":"status.json"}
```

Addresses are resolved relative to the configuration. Start `aethron-edge serve --config local.json`, then `python examples/clients/observe.py --token-file token --profile bench --limit 3`. `scripts/edge_package_check.py` exercises this from a fresh installed environment outside the checkout. Never put credentials in query strings or camera URLs in public logs.

File/RTSP profiles select `ffmpeg`; UVC profiles select the actual OS backend (`v4l2`, `avfoundation`, `msmf`) and an authorized device index. Pixel profiles require an explicit local pinned YOLOX model, lighting domain and optional vision dependencies. Generic OpenCV does not establish exposure timing: real decoding/inference runs, but current v3 evidence remains UNKNOWN when timing is unqualified. File and local RTSP tests are software evidence; virtual UVC tests do not qualify physical cameras. RGB is ineligible outside daylight under v3.

The API accepts only configured source-profile names. It has no arbitrary URL/file/model/command endpoint. Default loopback still requires authentication; cross-origin requests and token URLs are rejected. Remote binding is deliberately not exposed in this candidate: a separately configured authenticated TLS proxy can consume the protected local interface after its deployment is reviewed. No plaintext LAN listener is silently enabled.

GPL-3.0-only community licensing and separately negotiated commercial terms apply to project-owned code. Models, datasets and dependencies retain their own licenses. No online license heartbeat is required.
