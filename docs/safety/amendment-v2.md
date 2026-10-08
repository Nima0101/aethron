# AETHRON Safety Amendment v2 — transient human boxes + darkness continuity

This amendment corrects one over-broad rule from the frozen v1 safety constitution.

The original prohibition on all human bounding boxes was too broad for legitimate immediate collision-avoidance and rescue perception. That restriction is superseded by the narrower rules below.

This amendment MUST be preserved publicly as an explicit versioned correction. Do not rewrite history or silently edit v1.

All prohibitions on biometric identification, re-identification, covert tracking, targeting, person pursuit, threat scoring, through-wall person imaging and weapons remain unchanged.

## Transient human / pedestrian bounding boxes are allowed

A human/pedestrian may be represented by a temporary bounding box when:
- it is needed for immediate perception, collision avoidance, rescue visibility or safety response;
- the box is derived from current valid sensor evidence;
- the output contains no biometric identity;
- there is no stable person identifier;
- there is no cross-scene re-identification;
- there is no long-term trajectory/history;
- there is no target lock, pursuit or person-following behavior.

Permitted bounded fields may include:
- class = person/pedestrian;
- bounding box;
- confidence/uncertainty;
- range/depth where directly supported;
- relative motion needed for immediate collision avoidance;
- freshness;
- sensor/fusion provenance.

Any temporary internal association used for frame-to-frame stability must expire quickly and must not become a durable person identity.

## Darkness continuity is a safety requirement

Visible-light camera failure or near-zero illumination MUST NOT by itself remove a previously supported safety object if other valid sensors continue to support that object.

The perception stack must treat darkness as a sensor-degradation event, not as disappearance of the physical world.

When RGB becomes unusable:
- thermal may continue human/animal/hot-source localization where validated;
- radar/mmWave may continue occupancy/range/motion support where validated;
- depth/LiDAR may continue geometry where validated;
- fusion must reweight toward still-valid sensors;
- the displayed box must preserve provenance and uncertainty;
- the system must not claim RGB support when RGB is blind.

A detection may be withdrawn only when the remaining evidence no longer supports the claim under the frozen acceptance criteria.

## Safety behavior under uncertainty

For vehicles and drones, uncertainty must bias toward defensive behavior rather than pretending the path is clear.

Examples:
- uncertain pedestrian near vehicle path -> WARN / controlled STOP according to the declared controller contract;
- uncertain obstacle near drone path -> HOVER / STOP / LAND / RETREAT according to the declared controller contract;
- loss of one sensor while another remains valid -> degrade confidence and continue the supported object;
- loss of all supporting sensors -> UNKNOWN plus fail-safe action, not silent disappearance.

Do not promise zero accidents or perfect perception. Hardware and environment limitations remain explicit.

## Through-obstruction boundary remains unchanged

This amendment does NOT authorize precise through-wall human bounding boxes.

Through-obstruction sensing remains:
- coarse zone/sector presence;
- explicit uncertainty;
- no identity;
- no precise person trajectory;
- no reconstructed person image;
- no target continuity through structures.

A visible/thermal/range-based human box in open line-of-sight is different from a precise person box reconstructed behind a wall.

## Required implementation and verification updates

Astra must update, through versioned amendments/ADRs rather than silently modifying frozen v1 evidence:
- AGENTS.md;
- safety documentation;
- architecture invariants;
- public output schema;
- sensor capability matrix;
- verification matrix;
- darkness tests;
- temporal-association expiry tests;
- privacy/misuse tests;
- demos;
- README capability and limitation claims.

Add explicit tests proving:
1. a person box persists through RGB blackout when validated thermal/radar/depth evidence remains;
2. provenance changes when RGB drops out;
3. confidence/uncertainty changes honestly;
4. person association expires and cannot be reused as identity;
5. no re-identification after disappearance/re-entry;
6. all-sensor loss becomes UNKNOWN/fail-safe rather than "no object";
7. through-wall mode still cannot emit precise human boxes.

This v2 correction is mandatory for all later production/publication gates.

