# COCO-SSD Lite model (pretrained object-detection weights)

Upstream model repository: [TensorFlow.js Models — COCO-SSD](https://github.com/tensorflow/tfjs-models/tree/master/coco-ssd).
Original model distribution: [ssdlite_mobilenet_v2](https://storage.googleapis.com/tfjs-models/savedmodel/ssdlite_mobilenet_v2/model.json) hosted by Google. The TensorFlow.js Models source is Apache-2.0 licensed; pretrained weight redistribution provenance should be rechecked before a public release. No custom training, accuracy calibration or UAV model is claimed.

The six exact model files are bundled with the static browser app to eliminate inference-time cross-origin downloads and enable repeat offline loading. Binary hashes are checked by `python3 scripts/verify_web_model.py`. Inference runs in the browser using `@tensorflow/tfjs` and `@tensorflow-models/coco-ssd`; no frames or inference requests are sent to a server.

These generic COCO category detections are not safety-certified for rescue, driving or aerial navigation. The model does not establish visible-light detection performance in darkness and is not a dedicated small-aircraft or UAV detector.
