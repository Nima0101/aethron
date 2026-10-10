# Ingress measurement result admission — review v3

Baseline: `5f0f24ac72bbf0dddc1c95c4a705bc8ab56c89b5`. The continuation
verified the portable-corpus bridge commit and its source observations, checked
earliest declaration/artifact/campaign regressions, then read the source-observation,
measurement, review-driver and ingress-comparison implementations. Fifteen focused
earlier-boundary methods passed. The 65,536-byte ingress measurement discarded all
twenty timed results and the allocation-traced result. An incorrect returned report
could therefore accompany an apparently normal measurement report. Earlier files
remain historical observations; they do not establish measured-result correctness.

## Constraints and technology reassessment

The measured subject is the synchronous Python declaration API over one fixed
synthetic manifest padded with spaces to its upper byte limit. Twenty elapsed-time
samples and one Python-traced allocation peak are descriptive shared-host evidence.
They are not a steady-state benchmark, RSS ceiling, timing acceptance threshold,
Java performance measurement or physical real-time qualification. Validation must
observe every actual result and its Python types outside the measured interval.

| Candidate | Decisive property |
|---|---|
| Python perf_counter_ns/tracemalloc plus exact result checking | Observes the required in-process values, elapsed intervals and Python allocation scope without a serialization boundary. Requires explicit tracing ownership and a separately authored expected report. |
| pyperf worker orchestration | Credible for process isolation, calibrated repetitions and statistical benchmarking. That is a different measurement protocol from these finite descriptive samples; it still needs result correctness checks. |
| F#/C# with BenchmarkDotNet | Credible non-incumbent benchmark ecosystem. An external Python invocation measures process/interop costs and cannot itself inspect the original Python result types or substitute for the specified traced-allocation metric. Reassess for a .NET subject or installed-consumer comparison. |

**KEEP the in-process measurement; FIX result admission.** Direct observability of
the declared subject and metric is decisive, not familiarity, installed tools or
rewrite cost. No alternative was benchmarked and no performance ranking follows.
Sources inspected 2026-10-10:
[Python clock](https://docs.python.org/3.13/library/time.html#time.perf_counter_ns),
[Python allocation tracing](https://docs.python.org/3.13/library/tracemalloc.html),
[pyperf runner](https://pyperf.readthedocs.io/en/latest/runner.html), and
[BenchmarkDotNet overview](https://benchmarkdotnet.org/articles/overview.html).
The suitability comparison is this review's analysis.

## Correction and verification

The expected complete declaration report is authored from the reviewed synthetic
fixture: two sensors, six synthetic records, no findings, and false artifact and
physical verification flags. Its padded-input SHA-256 is a literal independently
computed from the fixture bytes and space padding, never from a validator result.
Every timed return is checked after stopping that timer. The traced return is
retained and checked after the shared helper has stopped its owned trace. Existing
source observations still bracket the workload. No declaration API, fixture,
threshold, transport format or qualification flag changed.

Three new methods exercise altered flags, values, exact scalar/container types,
hashes and extra fields on the first timed and traced calls, plus each remaining
timed call individually. Before correction these controls produced 43 assertion
failures and zero errors; the unchanged positive measurement passed. Failure now
raises `ingress_measurement_failed` before report output, with tracing released.
Report metadata explicitly records result checking, its exclusion from measured
intervals, and the expected input hash. Raw clocks still include call/assignment
and interpreter overhead; retaining the traced result changes its object lifetime.
Neither field is a pure algorithm-cost measurement.

Integration controls use synthetic Python-generated parser responses; they do not
claim Java execution. Hosted discovery includes the new methods, but this change
has not been verified remotely. Existing mismatch/negative evidence remains
visible. The results and source observations are in
[ingress-measurement-results-v3.json](ingress-measurement-results-v3.json).
Node hash-probe result admission and the remaining hosted verification review are
next. Full lane re-audit, installed P15/P19 acceptance and physical qualification
remain incomplete. Insufficient information for tactical deployment.
