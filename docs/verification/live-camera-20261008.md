# Cross-platform live camera preview evidence — 8 October 2026

- Browser build: `npm ci`, three Node unit tests and Vite production build passed on Mac mini.
- On-device preview: headless Chromium using a virtual 960px camera, genuine local COCO-SSD Lite inference and bundled weight files. CPU fallback worker processed frames but took **7533 ms** for one frame; the UI explicitly showed DELAYED. Stop responded in **198.16 ms**, disconnected every camera track and reported no page JavaScript errors. Virtual camera is not physical iPhone validation.
- Native video adapter: three frames from a generated local MJPEG recording passed through the pinned YOLOX Core ML detector (sample output contained 2, 1 and 1 detections). No controllers/RTSP hardware were exercised.
- Model integrity: six locally bundled browser model files passed SHA-256 verification before the web build.
- npm production dependency audit: zero reported known vulnerabilities after importing only TFJS core/converter/CPU/WebGL packages instead of the full metapackage.
- Existing core verification: 66 unit tests passed and the 100-frame 32-object synthetic benchmark passed at p95 8.875 ms on the local host. This is not browser inference latency.
- Public repository: [Nima0101/rescuesense](https://github.com/Nima0101/rescuesense), public snapshot intentionally uses a GitHub noreply identity to preserve commit email privacy.
- GitHub Pages: [RescueSense Camera](https://nima0101.github.io/rescuesense/), browser build and deploy workflow successfully completed. HTML, service worker and model index returned HTTP 200.

**Unqualified:** physical iPhone/Android Safari, mobile GPU throughput, offline restart behavior, UVC or RTSP from actual vehicle/drone cameras, model calibration, small aircraft recall, night/thermal sensing, certified automotive/UAS safety integration and independent conformity assessment. The 20/20 recorded aircraft misses from previous evaluations remain a known failure and no operational rescue approval has been issued.
