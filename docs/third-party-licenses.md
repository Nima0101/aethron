# Licenses and supply chain
Core runtime: Python standard library; no installed core runtime dependencies. Project-owned new software is GPL-3.0-only (see [licensing scope](../LICENSING.md)); existing historical Apache-2.0 grants remain valid. The original frozen rule-model file aethron/models/rules.json retains its embedded Apache-2.0 licence identifier for reproducibility, and third-party components keep their original licences. Optional vision uses separately installed NumPy/OpenCV, whose pinned versions and installed license-file hashes are recorded in the vision supply-chain evidence. Their native/transitive components remain external dependencies, not bundled in the zipapp. An additional optional macOS Core ML backend uses ONNX Runtime (MIT), FlatBuffers (Apache-2.0) and Protocol Buffers (BSD-3-Clause), pinned in `requirements-coreml.txt`, separately installed and inventoried when present. These native libraries are not bundled in the core archive; consult upstream license files and component inventory before redistribution.

External assets now present in v3:

- Amazon AOT evaluation pixels under [CDLA-Permissive-1.0](../data/aot/LICENSE.txt); [source, modification and attribution](../data/aot/README.md).
- NASA public-domain and Stefan van der Walt CC0 smoke photos; [exact provenance](../data/rgb-smoke/README.md).
- Separately fetched OpenCV Zoo YOLOX-S ONNX weights under the [model-specific Apache2 license](models/YOLOX-LICENSE.txt), SHA-256 verified before loading. [Model card](models/v3-model-card.md). Weights are not bundled in core artifacts.

The separate browser demo bundles a pretrained COCO-SSD Lite TensorFlow.js model (weights and JSON) and npm-distributed TFJS components. See the [asset provenance and redistribution note](../web/public/models/coco-ssd-lite/README.md); web app distribution must retain upstream license notices and complete the weight-license review prior to public release.

No Visage reference image or paid standards text is redistributed. Research pages are linked and concisely summarized. No GPL SORT code was copied; mathematical tracker/assignment implementation is original.

Development tools are pinned and excluded from executable artifacts. Release SBOM records application, runtime and dataset licensing plus optional dependency/model information; separate vision inventory records native-package license hashes. Provenance is local and unsigned until hosted attestation actually executes. Dependency scanning does not establish absence of vulnerabilities.
