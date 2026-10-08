// Off-main-thread fallback: CPU inference never blocks camera controls.
export class WorkerDetector {
  constructor() {
    this.worker = new Worker(new URL('./cpu.worker.js', import.meta.url), {type: 'module'});
    this.pending = new Map();
    this.serial = 0;
    this.worker.onmessage = ({data}) => {
      const operation = this.pending.get(data.id);
      if (!operation) return;
      this.pending.delete(data.id);
      if (data.success) operation.resolve(data.result);
      else operation.reject(new Error(data.error || 'worker_detection_failed'));
    };
    this.worker.onerror = (event) => {
      this.rejectPending(new Error('cpu_worker_failed'));
      event.preventDefault();
    };
  }
  rejectPending(error) {
    for (const op of this.pending.values()) op.reject(error);
    this.pending.clear();
  }
  dispatch(type, payload = {}, transfer = []) {
    return new Promise((resolve, reject) => {
      const id = ++this.serial;
      this.pending.set(id, {resolve, reject});
      try { this.worker.postMessage({id, type, ...payload}, transfer); }
      catch (error) { this.pending.delete(id); reject(error); }
    });
  }
  async init(url) { return this.dispatch('init', {url}); }
  async detect(video, maxBoxes = 20, minScore = 0.5) {
    const originalWidth = video.videoWidth, originalHeight = video.videoHeight;
    const scale = Math.min(1, 640 / originalWidth, 640 / originalHeight);
    const width = Math.max(1, Math.round(originalWidth * scale));
    const height = Math.max(1, Math.round(originalHeight * scale));
    const canvas = document.createElement('canvas');
    canvas.width = width; canvas.height = height;
    const context = canvas.getContext('2d', {willReadFrequently: true});
    if (!context) throw new Error('camera_frame_canvas_unavailable');
    context.drawImage(video, 0, 0, width, height);
    const pixels = context.getImageData(0, 0, width, height);
    const predictions = await this.dispatch(
      'detect', {width, height, buffer: pixels.data.buffer, maxBoxes, minScore},
      [pixels.data.buffer]
    );
    return predictions.map(p => ({
      ...p,
      bbox: [p.bbox[0] * originalWidth / width, p.bbox[1] * originalHeight / height,
             p.bbox[2] * originalWidth / width, p.bbox[3] * originalHeight / height]
    }));
  }
  terminate() {
    this.worker.terminate();
    this.rejectPending(new Error('worker_stopped'));
  }
}
