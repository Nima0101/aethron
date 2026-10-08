// Pure output and freshness logic shared by the camera UI and tests.
const CLASSES = new Set([
  'person','bicycle','car','motorcycle','bus','truck','train','boat',
  'dog','cat','bird','horse','sheep','cow','elephant','bear','zebra','giraffe',
  'traffic light','stop sign','fire hydrant','bench','chair','backpack'
]);

export function normalizedObservations(predictions, width, height) {
  if (!Array.isArray(predictions) || !(width > 0 && height > 0)) return [];
  return predictions.filter(p => CLASSES.has(p.class) && Number.isFinite(p.score)
    && p.score >= 0.5 && Array.isArray(p.bbox) && p.bbox.length === 4
    && p.bbox.every(Number.isFinite)).slice(0, 20).map(p => {
    const [x,y,w,h] = p.bbox;
    const left = Math.max(0, Math.min(width, x));
    const top = Math.max(0, Math.min(height, y));
    const right = Math.max(left, Math.min(width, x + w));
    const bottom = Math.max(top, Math.min(height, y + h));
    return { label: p.class, confidence: p.score, box: [
      left / width, top / height, (right - left) / width, (bottom - top) / height
    ] };
  }).filter(p => p.box[2] > 0 && p.box[3] > 0);
}
export function evidenceStatus(durationMs, maxAgeMs = 100) {
  if (!Number.isFinite(durationMs) || durationMs < 0) return 'UNKNOWN';
  return durationMs <= maxAgeMs ? 'CURRENT' : 'DELAYED';
}
export function cameraError(error) {
  if (!globalThis.isSecureContext || !navigator.mediaDevices?.getUserMedia)
    return 'Camera access requires HTTPS or localhost (and a compatible browser).';
  if (error?.name === 'NotAllowedError') return 'Camera permission denied. Enable camera access for this site.';
  if (error?.name === 'NotFoundError') return 'No compatible camera was found on this device.';
  if (error?.name === 'NotReadableError') return 'Camera is busy or unavailable. Close other camera apps and retry.';
  return 'Unable to open camera. Check device permissions and try again.';
}
