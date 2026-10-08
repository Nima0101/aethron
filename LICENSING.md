# AETHRON licensing

**Community/open-source edition: GNU GPL version 3 only (SPDX: GPL-3.0-only).**
**Alternative commercial licence: available separately from the rights holder, Nima Khaki.**

AETHRON uses dual-licensing for project-authored software over which the licensor controls all rights necessary for both grants:

1. **GPLv3** — Anyone can use, study, modify, and distribute covered code under the terms of [GNU GPL version 3](LICENSE). This **includes commercial and business use** if the GPL obligations are met. GPL is not a noncommercial licence; redistribution of covered binaries/derivatives triggers its applicable source and other requirements.
2. **Alternative commercial licence** — Individuals and organizations needing different distribution terms, for example incorporation of controlled AETHRON code into a proprietary product, can [request a separate licence](COMMERCIAL-LICENSING.md). No commercial licence is automatically granted by this repository. Fees, support, warranties and permitted redistribution require an executed agreement.

**The owner retains copyright.** Publishing under GPL does not assign ownership or prevent offering a nonexclusive second licence for code whose copyrights and third-party rights the licensor controls. The commercial grant does not automatically extend to third-party assets or contributions lacking express permission.

## Scope and exclusions

The repository's **original software** (Python runtime and scripts, original web app, and future project-owned platform integrations) is offered under GPL-3.0-only from this publication onward unless a specific file expressly states a different licence.

Third-party and separately licensed material keeps its own terms:

- **Amazon Airborne Object Tracking evaluation data**: CDLA-Permissive-1.0; see [data provenance](data/aot/README.md).
- **Photos**: NASA public domain and CC0 material; see [photo provenance](data/rgb-smoke/README.md).
- **Model weights and dependency libraries**: their respective upstream licenses apply, including Apache-2.0 YOLOX-S model weights and TensorFlow.js components; see [third-party licensing](docs/third-party-licenses.md). Bundling a component does not relicense it.
- **Original frozen rule model**: aethron/models/rules.json retains its embedded legacy Apache-2.0 identifier and SHA-256 to preserve benchmark reproducibility; the legacy licence marking is not permission to treat new AETHRON code as Apache-2.0.
- **Historical releases**: anyone who lawfully received an AETHRON version under Apache-2.0 retains those rights for that copy. This change does **not revoke** already granted licences, even if the project changes its default licence for future releases.

Commercial licensors must own or have permission to relicense *every relevant component* of what they offer. GPL and third-party licence compatibility must be evaluated for combined distributions; the commercial agreement cannot cancel independent upstream requirements.

## Future contributions

A standard pull request, DCO sign-off or GPL-only contribution does not automatically grant a right to relicense that contributor's copyright under a proprietary agreement. Before accepting third-party copyrighted code into the dual-licensable source, the maintainer needs an **explicit written permission/assignment** covering both GPL distribution and separate commercial relicensing, including any employer rights. See [contribution policy](CONTRIBUTING.md). This document is a policy, not a claim that agreements have been executed.

## Appliances, app stores and safety products

GPLv3 includes additional conditions for certain consumer-product distributions and installation information. OEM vehicle, drone, hardware appliance and App Store publishing paths must be checked for GPL compatibility, downstream installation/source obligations, platform terms and individual hardware/SDK rights. A separate commercial licence may provide another path **only** for software whose necessary rights are held by the commercial licensor; it does not remove third-party rights or safety regulations.

The unmodified [LICENSE](LICENSE) is the actual GPL grant. This explanatory file is not a substitute for legal review of a specific commercial deal.
