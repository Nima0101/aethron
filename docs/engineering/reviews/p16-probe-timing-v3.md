# P16 comparison timing review v3

Baseline: `8b4bdb04aef99a8c3b6de839f4133c079257efbd`. Reviewed 2026-10-10.
Decision: **KEEP in-process diagnostic clocks; MIGRATE Python readings to integer
nanoseconds; clarify batch scope**. The source-consistency bridge was verified against
its parent, five recorded file hashes and noreply identity before publication.

## Constraints and technology reassessment

This is an offline, bounded diagnostic of the existing passport implementation and an
independent Node primitive check. It must retain elapsed intervals and describe their
workload accurately. There is no target hardware class, scheduler configuration,
representative arrival process or physical latency requirement available to this probe.
It must not infer a language winner from a single local sample.

| Candidate | Evidence and decision |
|---|---|
| Python performance counter, integer readings | Python documents [perf_counter_ns](https://docs.python.org/3.13/library/time.html#time.perf_counter_ns) as avoiding floating-point precision loss. Select integer subtraction before conversion to the existing millisecond fields. Nanosecond units do not establish nanosecond accuracy. |
| Node performance.now | The [official API](https://nodejs.org/api/perf_hooks.html#performancenow) returns milliseconds relative to process start. KEEP this independent primitive diagnostic, closing the interval directly after the hash loop. It does not time a complete Node passport verifier. |
| pyperf calibrated repeated workers | [pyperf](https://pyperf.readthedocs.io/en/latest/run_benchmark.html) provides runs, values, warmups and loop calibration. Appropriate for a separately specified statistical benchmark; this correction makes no such claim and does not execute a multi-worker experiment. |
| Java/Kotlin with JMH | [JMH](https://github.com/openjdk/jmh) supports benchmarks for JVM languages, a credible ecosystem outside the current component languages. It measures JVM implementations or an explicit cross-process boundary; replacing this timer with a JVM orchestrator would not retain direct Python-call timing semantics. No JVM implementation or comparative performance advantage was demonstrated here. |

The choice follows the measurement boundary, not existing installation, familiarity or
rewrite cost. Integer clock arithmetic is the locally executable improvement and is
implemented now. No migration of passport admission follows from these samples.

## Corrected accounting

Previously the standalone report named a 1 MiB hash metric without recording that it
was sixteen independent SHA-256 operations on a reused 64 KiB buffer. The digest itself
covers 64 KiB. The Python verifier field is one batch elapsed interval divided by 128,
including loop and assertion overhead, not a distribution of 128 recorded latencies.
The old Python timer subtracted floating-point seconds. The Node timer ended during
output-object construction, after reading its version and copying preceding fields.

Python now subtracts integer nanoseconds and retains both raw batch intervals in an
additive `timing_method` object. Existing millisecond field names and Node response
fields remain compatible. Node ends its interval immediately after the loop. The new
metadata records operation counts, buffer size, one batch per metric, no target
qualification and no supported runtime ranking. Initialization, fixture validation,
Node process startup and allocation tracing are outside the Python verifier interval.
Timing includes elapsed scheduling delays; warmup is not controlled. There are no
percentiles, jitter measurements, worst-case bounds or end-to-end physical measurements.

One regression first failed on the old implementation with one assertion failure and
zero execution errors. It supplies integer clock origins at or above 2**63 and intervals
with residual nanoseconds, checks exact arithmetic and retained raw values, and counts
real verifier calls at all four clock reads: 6, 6, 6, 134. The final allocation check is
the 135th call. Node capture is stubbed in this arithmetic test; the separately retained
live run executes the real Node script. A formatting-only check initially failed and
was corrected. The first related-suite invocation also exposed the existing evidence
test module's top-level fixture import; it failed collection once. The corrected
invocation uses `PYTHONPATH=tests:.`, and both logs are retained. Historical measurements remain immutable and are not upgraded by this
new metadata.

[Results](p16-probe-timing-v3-results.json) bind source bytes, test log digests and the
live local report. No hard real-time, MLS, CNSA, five-nines or physical qualification
is established. Insufficient information for tactical deployment.

The review remains incomplete. Next: the trust mutation runner's source consistency
and evidence lifecycle, which the comparison-only source correction did not cover.
