import './style.css';
import { cameraError, evidenceStatus, normalizedObservations } from './logic.js';
import { WorkerDetector } from './worker-client.js';

const $ = id => document.getElementById(id);
const video = $('video');
const overlay = $('overlay');
const ctx = overlay.getContext('2d');
const controls = { start: $('start'), switch: $('switch'), stop: $('stop') };
let stream = null, detector = null, timer = null, running = false;
let cpuWorker = null;
let session = 0, facing = 'environment', modelBackend = 'not-loaded';

function status(label, description, level = '') {
  $('health').textContent = label;
  $('health').className = 'health ' + level;
  $('message').textContent = description;
}
function controlsEnabled(active, loading = false) {
  controls.start.disabled = active || loading;
  controls.stop.disabled = !active && !loading;
  controls.switch.disabled = !active || loading;
}
function clearOverlay() {
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  $('detections').replaceChildren();
  $('count').textContent = '0';
}
function closeStream() {
  if (stream) {
    for (const track of stream.getTracks()) track.stop();
    stream = null;
  }
  video.pause();
  video.srcObject = null;
}
function stopCamera(message = 'Camera stopped. No video has been saved.') {
  session++;
  running = false;
  if (cpuWorker) {
    cpuWorker.terminate();
    cpuWorker = null;
    detector = null;
  }
  if (timer !== null) clearTimeout(timer);
  timer = null;
  closeStream();
  clearOverlay();
  $('empty').hidden = false;
  $('frame-latency').textContent = '— ms';
  controlsEnabled(false);
  status('OFFLINE', message);
}
function render(observations, width, height, inferenceMs) {
  const dimensions = overlay.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  overlay.width = Math.max(1, Math.round(dimensions.width * scale));
  overlay.height = Math.max(1, Math.round(dimensions.height * scale));
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, dimensions.width, dimensions.height);
  const factor = Math.min(dimensions.width / width, dimensions.height / height);
  const drawnW = width * factor, drawnH = height * factor;
  const offsetX = (dimensions.width - drawnW) / 2;
  const offsetY = (dimensions.height - drawnH) / 2;
  const isDelayed = evidenceStatus(inferenceMs) !== 'CURRENT';
  const color = isDelayed ? '#ffbb77' : '#6ce9c2';
  ctx.font = 'bold 13px ui-sans-serif, system-ui';
  ctx.lineWidth = 2.5;
  $('detections').replaceChildren();
  $('count').textContent = String(observations.length);
  for (const object of observations) {
    const [x,y,w,h] = object.box;
    const boxX = offsetX + x * drawnW, boxY = offsetY + y * drawnH;
    const boxW = w * drawnW, boxH = h * drawnH;
    ctx.strokeStyle = color;
    ctx.strokeRect(boxX, boxY, boxW, boxH);
    const label = object.label + ' ' + Math.round(object.confidence * 100) + '%';
    const textWidth = ctx.measureText(label).width + 14;
    const labelY = Math.max(0, boxY - 26);
    ctx.fillStyle = '#081c22e8';
    ctx.fillRect(boxX, labelY, textWidth, 24);
    ctx.fillStyle = color;
    ctx.fillText(label, boxX + 7, labelY + 17);
    const item = document.createElement('li');
    const name = document.createElement('b');
    name.textContent = object.label;
    item.append(name, document.createTextNode(' ' + Math.round(object.confidence * 100) + '%'));
    $('detections').append(item);
  }
}
async function inferenceStep(currentSession) {
  if (!running || currentSession !== session || document.hidden) return;
  if (!video.videoWidth || !video.videoHeight) {
    timer = setTimeout(() => inferenceStep(currentSession), 120);
    return;
  }
  const capturedAt = performance.now();
  try {
    const predictions = await detector.detect(video, 20, 0.5);
    if (!running || currentSession !== session) return;
    const duration = performance.now() - capturedAt;
    const observations = normalizedObservations(predictions, video.videoWidth, video.videoHeight);
    render(observations, video.videoWidth, video.videoHeight, duration);
    $('frame-latency').textContent = Math.round(duration) + ' ms';
    if (evidenceStatus(duration) === 'CURRENT') {
      status('OBSERVING', observations.length + ' unverified visual observations. Camera stays local.', 'ready');
    } else {
      status('DELAYED', 'Inference exceeded 100 ms. The observations are not fresh enough for safety decisions.', 'stale');
    }
  } catch (error) {
    if (currentSession !== session) return;
    stopCamera('Inference failed; observations withdrawn. ' + String(error?.message || error).slice(0, 160));
    return;
  }
  timer = setTimeout(() => inferenceStep(currentSession), 90);
}
async function loadDetector() {
  if (detector) return;
  status('LOADING MODEL', 'Preparing local object detector. The first run may take longer.', 'busy');
  const modelUrl = new URL('./models/coco-ssd-lite/model.json', document.baseURI).href;
  const cpuOnly = new URLSearchParams(location.search).get('backend') === 'cpu';
  if (!cpuOnly) {
    const [tf, cocoSsd] = await Promise.all([
      import('@tensorflow/tfjs-core'),
      import('@tensorflow-models/coco-ssd'),
      import('@tensorflow/tfjs-backend-webgl')
    ]);
    await tf.ready();
    let webgl = false;
    try { webgl = await tf.setBackend('webgl'); } catch { /* worker fallback */ }
    if (webgl) {
      await tf.ready();
      modelBackend = 'webgl';
      $('engine').textContent = 'COCO-SSD · WebGL · on-device';
      detector = await cocoSsd.load({base: 'lite_mobilenet_v2', modelUrl});
      return;
    }
  }
  cpuWorker = new WorkerDetector();
  await cpuWorker.init(modelUrl);
  detector = cpuWorker;
  modelBackend = 'cpu-worker';
  $('engine').textContent = 'COCO-SSD · CPU worker · on-device';
}
async function startCamera() {
  if (running || !navigator.mediaDevices?.getUserMedia || !globalThis.isSecureContext) {
    status('UNAVAILABLE', 'Camera requires HTTPS or localhost and a compatible browser.', 'stale');
    return;
  }
  const currentSession = ++session;
  controlsEnabled(false, true);
  status('STARTING', 'Requesting access to your camera…', 'busy');
  try {
    const opened = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: facing }, width: { ideal: 960 }, height: { ideal: 540 } },
      audio: false
    });
    if (currentSession !== session) {
      opened.getTracks().forEach(track => track.stop());
      return;
    }
    stream = opened;
    video.srcObject = opened;
    await video.play();
    if (currentSession !== session) return;
    $('empty').hidden = true;
    await loadDetector();
    if (currentSession !== session) return;
    running = true;
    controlsEnabled(true);
    status('PROCESSING', 'Camera open. First inference in progress.', 'busy');
    inferenceStep(currentSession);
  } catch (error) {
    if (currentSession !== session) return;
    const reason = stream
      ? 'Local detection model failed: ' + String(error?.message || error).slice(0, 120)
      : cameraError(error);
    stopCamera(reason);
    status('UNAVAILABLE', reason, 'stale');
  }
}
controls.start.addEventListener('click', () => startCamera());
controls.stop.addEventListener('click', () => stopCamera());
$('compat').addEventListener('click', () => {
  stopCamera('Switching to CPU worker mode');
  const url = new URL(location.href);
  url.searchParams.set('backend', 'cpu');
  location.assign(url.href);
});
controls.switch.addEventListener('click', () => {
  facing = facing === 'environment' ? 'user' : 'environment';
  stopCamera('Switching camera');
  startCamera();
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden && stream) stopCamera('Camera paused when the app was hidden. Tap Start to resume.');
});
window.addEventListener('pagehide', () => { if (stream) stopCamera(); });
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  navigator.serviceWorker.register(new URL('./sw.js', document.baseURI)).catch(() => {});
}
status('OFFLINE', 'Ready. Tap Start camera. Camera and inference run on this device.');
