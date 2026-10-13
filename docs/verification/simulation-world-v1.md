# Synthetic world-to-defensive integration evidence v1

Software-only evaluation; no physical sensing, motion authority, hardware timing,
field accuracy, certification or production claim. The technology and boundary
are recorded in [the design](../architecture/simulation-world-v1.md).

RED retained: the initial 11 integration cases could not import
`aethron.simulation_world`. After composition, all 11 passed. Extending the
resource probe first failed with `TypeError: SimulatedWorld.step() missing 2
required keyword-only arguments: 'coordinate_frame' and 'clock_domain'`.
The adapter path now supplies mandatory context and rejects loss of current
support with `lost_current_evidence`. Initial Ruff findings C408/E702 in the new
test were corrected before validation.

Focused checks on Linux / Python 3.13.5:

- 11 new adapter cases plus 9 P5 admission cases: PASS.
- 18 world cases plus 4 resource-report/probe cases: PASS.
- 21 temporal cases plus 1 bounded-recommendation case: PASS.
- Ruff check/format and Bandit on changed executable paths: PASS.
- 64 seeded bounded malformed-byte cases and 4 recovery/loss outputs satisfy
  the unchanged P5 response schema; no unexpected exceptions: PASS.
- Nine frozen manifests, source hashes and public-content/link checks: PASS.

Tests exercise real P6 and P5 implementations. Original acquisition timestamps
survive processing delay; sensor/calibration expiry is never extended; valid
thermal support survives RGB darkness with the negative RGB diagnostic retained.
Prediction-only/empty scenes remain UNKNOWN. Unsupported provenance/policy is
quarantined before world state admission. Invalid clocks, frames, malformed bytes,
watchdog loss, watermarks, close and returned-object mutation are covered. No
track identifiers, boxes, range or predicted motion leave the adapter.

Reproduce the bounded measurement (not the full repository suite):

```sh
python3 scripts/world_technology_probe.py --out build/p6-world/simulation-world-resource.json
```

[Raw evidence](simulation-world-resource-v1.json) retains all 100 wall samples
per path, source/workload hashes and separate memory measurements. Workload and
thresholds match the frozen v3 100-frame/32-object workload.

| Path | p50 ms | p95 ms | max ms | Traced peak bytes |
| --- | ---: | ---: | ---: | ---: |
| Session | 2.611 | 4.863 | 63.724 | 121769 |
| WorldModel | 3.237 | 61.887 | 64.473 | 138893 |
| SimulatedWorld | 4.320 | 60.653 | **121.803** | 170165 |

All p95 samples fit the unchanged 100ms gate and traced peaks fit 32MiB.
**The adapter maximum exceeds 100ms.** The frozen gate is p95, not maximum;
this observed tail is retained and forbids treating the sample as a per-frame
or hard-real-time guarantee. Scheduling causes are not established. This is a
same-runtime composition comparison, not a cross-language speed ranking.
Earlier negative measurements remain unchanged. Full hosted publication gates
and external physical qualification remain outstanding.
