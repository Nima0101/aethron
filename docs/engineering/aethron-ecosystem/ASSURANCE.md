# Conditional assurance and operational qualification

This is an applicability worksheet for an engineering plan, not legal approval or a standards compliance assessment. Official public summaries were researched on 2026-10-08; clause-level paid standards, local implementing law and exact intended use require competent review before field deployment. No safety integrity level, certification or regulatory approval is assigned to AETHRON.

| Reference / geography | When it may apply | Concrete work product / decision owner |
|---|---|---|
| ISO 26262:2018 family, road vehicles | Safety-related E/E integration, especially a driving/defensive control function | Item definition, hazard analysis, safety goals/ASIL determination, safety plan, verification and independent assessment; vehicle system integrator [S34](SOURCES.md#s34) |
| ISO 21448:2022 SOTIF | Hazards from perception insufficiency/foreseeable misuse, even fault-free code | Intended operational domain, triggering conditions, scenario coverage, uncertainty/abstention and validation argument; perception + system owner [S35](SOURCES.md#s35) |
| ISO/SAE 21434:2021 | Automotive cybersecurity lifecycle | TARA, security requirements, supplier/update/incident process; cybersecurity owner [S36](SOURCES.md#s36) |
| UN R155/R156 in adopting jurisdictions | Applicable vehicle type approval and cybersecurity/software-update management | Applicability with homologation authority, CSMS/SUMS responsibilities, change impact; manufacturer/integrator. Not a blanket certification duty for every Python library [S37](SOURCES.md#s37) |
| ISO 16750-2:2023 | Road-vehicle electrical loads for relevant components | Power transient/brownout tests against exact installation; excludes motorcycle/moped environmental scope and EMC [S54](SOURCES.md#s54) |
| IEC 60825-1:2014 / IEC 62471:2006 | Laser versus lamp/LED active sensing/illumination | Product exposure/classification assessment including optics, mount and fault conditions; qualified optical safety evaluator [S55](SOURCES.md#s55), [S56](SOURCES.md#s56) |
| EU/EASA UAS; Sweden | Open/specific/certified category and national zones depend on flight/aircraft | Pilot/operator registration/competence, airspace/night/VLOS permissions, payload modification assessment, Swedish dissemination review; operator [S38](SOURCES.md#s38), [S39](SOURCES.md#s39) |
| United States FAA | Part 107 or other applicable operating authority, Remote ID/airspace | Qualified operator, night/airspace/over-people conditions, registration/Remote ID or valid exception; operator [S40](SOURCES.md#s40), [S41](SOURCES.md#s41) |
| EU GDPR/EDPB and local camera laws | Processing identifiable imagery, especially public/workplace areas | Lawful basis, transparency, minimization, retention, access rights and DPIA when required; data controller [S42](SOURCES.md#s42) |

If the installation is machinery rather than a road vehicle, assess the relevant machinery functional-safety/product standards separately instead of declaring ISO 26262 universal. Radio/EMC, electrical enclosure, ingress, vibration, battery and product market-access obligations need a per-SKU jurisdictional checklist at hardware selection. They are not satisfied by CE-marked component shopping or a software test suite.

## Field qualification sequence

Define intended users, environment, classes and prohibited use. Perform hazard analysis including false reassurance, missed/false alarms, stale geometry, driver/pilot distraction and unsafe downstream reliance. Preregister measurable requirements by class/condition and confidence interval; choose sample sizes from required failure-rate bounds before collection. Qualify a stationary instrumented bench with clock/latency ground truth, then controlled closed-site scenarios with an independent observer, then authorized representative trials. Keep consent/lawful-basis/notice records, calibrated sensor metadata and redacted result hashes.

Changes in lens, mount, firmware, driver, quantization, model weights, camera clock, display path or controller invalidate the relevant portion of the qualification record. Use a change-impact matrix to determine which tests repeat. No substitution of a synthetic pass for a physical failure. A benign demo, install success or exact-SKU video display does not establish safe detection performance.

## Defensive-control lifecycle, future only

Observation and advisory output can be useful while all actuators remain disconnected. A future owner-authorized bounded defensive integration must first establish system requirements, approved action semantics, hazard/failure analysis, independent watchdog, manual override and simulations including unsafe-to-stop/hover/land cases. Then isolated hardware-in-loop tests and external assurance precede field actuation. The core cannot choose a universally safe action from missing evidence. Weapon integration, targeting and following/pursuit remain prohibited regardless of any future phase approval.

## Licensing and operations

Document source, model, dataset, codec and SDK terms independently; review export/use restrictions where relevant to selected sensors/software and jurisdiction. Proprietary access requires explicit provider authorization. Security fixes need signed updates, rollback and disclosure handling; privacy-preserving aggregate telemetry is opt-in. Logs must not become a durable person history. Operators own flight/driving/site authority, and maintainers own accurately scoped software claims. None of those roles is silently delegated to a package installer.
