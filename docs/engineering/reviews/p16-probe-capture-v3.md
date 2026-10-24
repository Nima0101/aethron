# P16 comparison capture review v3

Baseline: `0d94c633b0aae5b9b595f01ac3320e5bfc3be708`.
Decision: **KEEP Python driver; FIX output accumulation and diagnostic handling**.
The four-file response-validation bridge matches the requested source hashes and
noreply identity. The earliest parser boundary was re-read and its tests rerun.

## Constraints and alternatives

A local probe exchanges at most 64 KiB of synthetic inputs with one reviewed child
script. It needs at most 4 KiB from each output stream, rejection on child failure,
and cleanup before returning evidence. This is assurance tooling, not operational
transport. Software targets include Python 3.9/3.13 on Linux, macOS and Windows;
this change has local execution evidence only on Linux Python 3.13.5.

| Candidate | Evidence and decision |
| --- | --- |
| Python subprocess/asyncio | [Communicate buffers output](https://docs.python.org/3.13/library/asyncio-subprocess.html), so a later size check is insufficient. [Subprocess protocol callbacks](https://docs.python.org/3.13/library/asyncio-protocol.html#subprocess-protocols) permit counting before accumulation and transport closure on overflow. KEEP with this executable correction. |
| Node child_process | [maxBuffer and timeout](https://nodejs.org/api/child_process.html) are credible built-in capture controls. A Node driver would still need to invoke the real Python verifier through a binding or process; this probe already uses Node independently for primitive comparison. No measured end-to-end benefit establishes a migration win. |
| Rust Tokio | [Process handles and asynchronous pipes](https://docs.rs/tokio/latest/tokio/process/index.html) support a native capture implementation; explicit limits and cleanup remain application responsibilities. No native deployment requirement justifies adding a separate driver boundary here. |
| Java/Kotlin Process | [Streams, exit waiting and destruction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Process.html) provide a credible option outside the current component languages. It likewise requires application stream limits and a verifier binding. No JVM deployment constraint is present. |

The selection follows the direct-verifier requirement and a small, explicit capture
boundary, not installed tooling or familiarity. The callback approach deliberately
avoids an accumulating StreamReader/communicate call. Alternative implementations
were researched, not benchmarked; this record makes no speed ranking.

## Executable correction

Previously `capture_output=True` accumulated stdout and stderr before the response
validator could enforce 4096 bytes. The extracted baseline retained this behavior.
Five focused negative assertions then failed: stdout overflow, stderr overflow,
input admission and the stable diagnostic expectations for timeout/nonzero exit.
The first test draft had three assertion failures and two unexpected exception
errors; the corrected controls retained five assertion failures and no errors.
Nonzero exit and timeout already rejected in the old implementation: those two
changes normalize diagnostics, not repair a false-success path.

The new private capture helper rejects inputs above 65536 bytes before creating an
event loop. Each output callback counts bytes before extending the stdout bytearray;
stdout accumulation never exceeds 4096 bytes. Stderr is counted and discarded.
Overflow closes the transport and rejects. Success requires pipe completion and a
zero exit status. The driver emits no comparison report on capture failure.
Exchange timeout is 15 seconds; teardown has a separate five-second cooperative
wait. Failure codes exclude raw child output. Transport close requests termination
of the direct child and closes its pipes. A real timeout test observes a completed
child return code and closed transport before the helper returns failure.

[Results](p16-probe-capture-v3-results.json) bind current source and the live run.
All 54 passport-family methods pass, including real subprocess overflow, exact-limit
round-trip, nonzero exit and timeout cases; earlier response and optimization controls
remain active. Ruff, formatting, Bandit (B101 excluded for probe assertions), source
bindings and diff checks pass. Runtime modules and wire contracts are unchanged.

## Limits and remaining work

This caps retained output accumulation, not total RSS, kernel/transport chunks,
child memory or child CPU. OS process creation precedes the exchange timeout;
scheduling and teardown are not hard real-time bounds. Descendant processes are
not managed. Executable paths remain trusted local configuration. No public-service
sandbox, device qualification or real-time performance is established. Insufficient
information for tactical deployment.

The [previous capture limitation](p16-probe-response-v3.md) describes its historical
baseline. This record supplies the correction. Next reconcile the V3 inventory and
source evidence through this commit before new P16 work. P17/P18 remain incomplete;
no audit-completion marker is created by this change.
