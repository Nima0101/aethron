import * as tf from '@tensorflow/tfjs-core';
import '@tensorflow/tfjs-backend-cpu';
import * as cocoSsd from '@tensorflow-models/coco-ssd';

let model = null;
self.onmessage = async event => {
  const { id, type, url, width, height, buffer, maxBoxes, minScore } = event.data;
  try {
    if (type === 'init') {
      await tf.setBackend('cpu');
      await tf.ready();
      model = await cocoSsd.load({base: 'lite_mobilenet_v2', modelUrl: url});
      self.postMessage({id, success: true, result: 'cpu-worker'});
    } else if (type === 'detect') {
      if (!model) throw new Error('worker_model_not_initialized');
      const pixels = new ImageData(new Uint8ClampedArray(buffer), width, height);
      const result = await model.detect(pixels, maxBoxes, minScore);
      self.postMessage({id, success: true, result});
    }
  } catch (error) {
    self.postMessage({id, success: false, error: String(error?.message || error).slice(0, 160)});
  }
};
