# Phase 1 checkpoint handoff — final validation in progress

Branch: `feat/aethron-vehicle-uav-preparation-20261008`. Phase 0 `58a2a9d`, public-main integration `8d0da0e`, owner approval `1445f18`. Implementation checkpoints: `947b72d`, `e5335ec`, `2739360`, `f4db8ce`, `04f6dec`, `e494cb0`; subsequent candidate work is being validated before its next local commit. No public operation or Phase 2 advancement.

The actual install/service/appliance entry points are [edge usage](../../usage-edge.md) and [appliance usage](../../usage-appliance.md). Strict contracts and platform fixture handoff are in [contracts](../../../contracts/README.md). The Linux guest is a signed software-in-loop image, not an automotive/UAS-qualified image.

Completed checks include a 46-test integration run, three real-pixel pipeline checks plus the subsequent worker-descendant crash regression, strict TypeScript tests, installed Python/TypeScript consumers, reproducible wheels, repository governance/data/core checks, both required fuzzers and corrected README visual reproduction. Final source-bound package/container/boot/clean-clone evidence is still being assembled; this checkpoint does not claim full Phase 1 acceptance.

Read [EXECUTION](EXECUTION.md) and [TEST-EVIDENCE](TEST-EVIDENCE.md) for limits and retained failures. Original Phase 0 handoff remains in commit `58a2a9d`; original aircraft and latency failures remain intact. Current physical OEM, UVC, zero-visible, power/thermal, field and certification claims remain unqualified. Hosted CI and unavailable native OS runners are not represented as executed.
