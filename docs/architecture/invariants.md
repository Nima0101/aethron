# Architecture invariants v1
I01 Strict versioned bounded input; reject unknown/duplicate fields, malformed numerics and unsupported combinations.
I02 Validate clock domain, age, skew and calibration before any positive observation contributes.
I03 Bad quality, dropout, saturation, occlusion, model failure and timeout withdraw dependent claims; UNKNOWN never becomes SAFE.
I04 Contradictory valid observations of the same capability/zone yield UNKNOWN. Do not multiply correlated scores into fake certainty.
I05 No identities, human geometry, raw sensing, persistent history or cross-zone continuity in public state/output.
I06 Through-obstruction mode: explicit authorization, coarse fixed zones, no imagery, precise location, trajectory, vitals or raw export.
I07 Outputs identify their limitations and uncertainty; scores do not claim empirical probability without calibration evidence.
I08 Warnings/recommendations expire. Controller actions require declared platform and integration contract; no direct actuator or navigation interface.
I09 Work, byte, record and sample limits tested; no network or executable model load.
I10 Evidence labels synthetic/live are immutable through processing; never claim hardware provenance from caller input alone.
I11 Every missing required capability is explicit UNKNOWN; single-sensor operation declares degradation.
I12 Malformed input produces a fixed error and no permissive result; watchdog/controller must independently handle process death.
