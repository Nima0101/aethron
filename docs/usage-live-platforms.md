# Run AETHRON on phones, laptops and video sources

## Live browser camera

The self-contained `web/` camera application requests the browser's native camera permission. The model runs **on the local device** in TensorFlow.js, with local weights (COCO-SSD Lite, 80-class vocabulary). Video pixels are not uploaded, saved or streamed by AETHRON. It uses the available browser WebGL backend, falling back to CPU where necessary; `?backend=cpu` forces a diagnostic CPU path.

```sh
cd web
npm ci
npm test
npm run dev
```

Open http://localhost:5173 on the same laptop and tap **Start camera**. The application supports switching the active camera and stopping all tracks. `npm run build` produces `web/dist` for ordinary HTTPS static hosting (for example GitHub Pages or another HTTPS server).

**iPhone/Android anywhere:** publish `web/dist` to a real HTTPS URL first, then open it in Safari/Chrome on the phone, grant camera access and optionally Add to Home Screen. HTTP LAN addresses and `file://` cannot be relied on for iOS camera access; `localhost` is permitted only on the same device. A public research preview is now hosted at **[nima0101.github.io/aethron](https://nima0101.github.io/aethron/)** (GitHub Pages). The HTML, model index and service worker returned HTTP 200 after a successful hosted build/deploy; this is not proof of physical iPhone or hardware compliance. After a successful online visit, the service worker can cache the app and model for repeat offline loads subject to browser storage policies.

When mobile hardware or headless browser inference takes longer than 100 ms, the UI labels observations **DELAYED**. A visible box is not a validated distance, an obstacle-avoidance guarantee, a drone classification or a declaration that conditions are safe. Camera-only vision cannot provide thermal sensing in zero visible light.

## Native host camera and vehicle/drone camera streams

Optional Python OpenCV backend accepts UVC camera indexes, local video and an RTSP-capable OpenCV input. Detection uses the pinned AETHRON YOLOX model, with optional Core ML acceleration on compatible Apple Silicon hosts:

```sh
.venv/bin/python scripts/live_video.py --source 0 --backend coreml
.venv/bin/python scripts/live_video.py --source /path/to/recording.mp4 --backend opencv
.venv/bin/python scripts/live_video.py --source 'rtsp://HOST/live' --backend opencv
```

The last example requires an existing authorized compatible stream and decoder; no video endpoint, camera, vehicle bus, drone SDK, remote access or driving controller is provisioned by this command. Output is observation-only JSONL; no raw pixels are retained. Capture transport age cannot be confirmed from `cv2.VideoCapture`, so each emitted safety state is UNKNOWN and there are no actuator commands. Real device and stream compatibility must be measured per platform.

## Safety engineering and platform verification

The development scope includes mobile, Windows/macOS/Linux, vehicles, drones and compatible sensors. They share data contracts and perception logic, but **validation is hardware- and operating-domain-specific**. A browser demo is not certification or regulatory approval.

For any safety-related deployment, the team must establish the precise vehicle/UAV/sensor configuration and applicable requirements; independently assess hazards, privacy and security; prove time synchronization, perception accuracy on representative held-out day/night and adverse-weather scenarios, quantified uncertainty, fail-safe state transitions and end-to-end latency; perform field and hardware-in-loop tests; and seek appropriate external assessment/approval. No generic certification can be issued for every possible camera/vehicle/drone.

This is an implementation roadmap, not a restriction against building additional platform adapters. Missing real hardware prevents claims of qualification, **not implementation of testable integrations**.
