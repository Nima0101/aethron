# Declaration output boundary review v3

Baseline: `21a67bd11b1024a1ef037953a0623f1f89aaa48f`. The current policy and review
order were reread after tool execution recovered. The Java transport bridge was
verified with its five intended files and noreply identity; committed-tree links
passed and that commit was pushed. Its exact-head CI observation was queued, so
no hosted pass or merge is claimed.

The review restarted with declaration parsing and findings, artifact binding,
campaign multiplicity, opaque procedure/domain references, bundle composition
and both command adapters. Thirty-seven focused baseline methods passed. These
APIs preserve separate physical/authenticity gates and do not operate hardware.
The current correction concerns the earlier declaration command's output boundary;
it does not close the entire P4/P15 review or introduce a new capture capability.

## Deployment and technology decision

The boundary is one synchronous source-checkout invocation with a bounded manifest,
a supplied evaluation instant and a small minimized JSON report on standard output.
It needs exact existing report bytes, explicit error handling and one unambiguous
return status from `main()`. No service, device ABI, persistent store or hard deadline
is specified. Ordinary redirected stdout may buffer; callers own supervision.

| Candidate | Decisive properties for this boundary |
|---|---|
| Python JSON plus explicit checked print/flush | Serializes the directly returned report without an interprocess adapter; handles write and flush exceptions in the same boundary as input errors. |
| C#/F# Console.Out / TextWriter | Credible standard-output abstraction, including redirection. A new host still needs explicit write/error handling and exact serializer/validator contract parity. |
| Rust Write | Explicit fallible writes and flush offer a credible native endpoint. A native validator or binding would be needed; ownership does not make report delivery atomic or acknowledge its consumer. |
| A supervised service or queue | Can support retries and acknowledgements under a separately specified protocol, but changes this one-shot local interface and its delivery semantics. It does not repair the current command by itself. |

**KEEP Python for this command; FIX the output boundary.** Direct composition keeps
one exact report representation and the existing error/serialization contracts.
The defect is demonstrated output lifecycle handling, with no measured native-runtime
advantage or target ABI requirement. This is not an installation, familiarity or
rewrite-cost argument. A durable delivery, service isolation or target latency
requirement would reopen the choice; none is established by these tests.

Primary sources inspected for the mechanism:
[Python print](https://docs.python.org/3.13/library/functions.html#print),
[Python stream flushing](https://docs.python.org/3.13/library/io.html#io.IOBase.flush),
[.NET Console.Out](https://learn.microsoft.com/en-us/dotnet/api/system.console.out?view=net-9.0),
and [Rust Write](https://doc.rust-lang.org/std/io/trait.Write.html#method.flush).
The suitability judgment is this review's inference. No relative runtime performance
or certification claim is derived from those documents.

## Defect, correction and limits

The old command put `print` outside its error handler and did not request a flush.
A failing write escaped `main()` as an exception. A buffered stream with a failing
flush returned declaration success because that flush was never attempted. Process
shutdown could subsequently fail; the old behavior did not prove successful delivery.

The corrected command serializes, writes and flushes inside the existing error
boundary. A caught write/flush error returns 2 and emits the fixed diagnostic if
stderr works. The existing successful and negative report bytes and statuses remain
unchanged. No error message from the output exception is included by `main()`.
Three synthetic stream tests first failed with four assertions and zero errors.
After correction they pass, alongside seven existing declaration/bundle process
tests. The positive controls retain both successful and expired-calibration goldens.

An output failure can occur after some or all JSON has already been written; this
cannot be retracted. Consumers must require a complete report and successful process
status. A flush transfers buffered data toward the underlying stream; it does not
prove durable storage, downstream processing, authenticity or physical qualification.
Python shutdown can retry flushing and independently change final process status or
diagnostics. A broken stderr also prevents the fixed diagnostic. The tests exercise
`main()` with controlled streams, not all OS/interpreter teardown paths. The README
now states these limits. There is no retry loop, filesystem redirection, global
stream replacement, new output field or altered frozen qualification threshold.

Source-bound evidence is in [report-output-review-v3.json](report-output-review-v3.json).
Historical result files remain unchanged. P15 producer integration and the remaining
audit-driver/source inventory still require review; no audit-complete marker is set.
