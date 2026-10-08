> Historical v0.1 evidence/procedure. See the [current v3 record](models/v3-model-card.md).

# Rule model card
Artifact: `rescuesense/models/rules.json`, Apache-2.0, original declarative rules by this project with AI assistance. No training or third-party weights. SHA-256 is pinned in the loader and release manifest. Loader verifies exact bytes and parses JSON; no executable deserialization. Invalid or missing model withdraws all dependent claims.

Thermal thresholds (0/60/150 C) and obstacle threshold (2 m) are frozen synthetic reference parameters, not certified operating limits. High/medium confidence is an uncalibrated score bucket. Hot equipment may produce a fire-like cue; temperature cannot establish ignition or person class. RGB/thermal_person/depth_person/radar scores come from external minimized classifiers or synthetic examples; the package does not supply those learned classifiers. Physical accuracy, calibration and license/provenance qualification remain blocked.

[Evaluation protocol](verification/evaluation-protocol.md) and its [coverage strengthening](verification/evaluation-protocol-v2.md) disclose the 320-case synthetic corpus, known false positives/negatives and missingness. No train/test overlap claim arises: there is no training. Reproduction: `python3 scripts/evaluate_dataset.py --write`. These fixtures validate software semantics, not real-world generalization.
