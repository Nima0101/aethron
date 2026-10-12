# Qualification CLI shutdown review — 2026-10-10

Baseline: `9e0fcbd5f5a04ce461bdf8c9898957c03dc5527a`. The previous bridge commit
and its source observations were verified. Review restarted at the declaration,
artifact and campaign boundaries, then followed the declaration command, opaque
reference binding, bundle composition and binary command into process shutdown.
The earlier CLI review explicitly retained shutdown as an unverified limitation.
This correction closes one reproduced process-level failure; it does not claim
every possible interpreter or operating-system teardown path.

## Reproduced failure and correction

Both commands caught a failed report flush and returned 2 from `main()`, but
ordinary Python module shutdown retried the buffered stdout flush. With no pipe
reader, four real subprocess cases returned 120 and added an interpreter error
after the fixed diagnostic. These cover positive and negative declaration
reports and positive and negative bundle reports. Two malformed-input controls
already returned the required fixed failure without a report.

The new private process-finalization helper closes stdout after status 2 before
raising `SystemExit`. A close error keeps status 2: it cannot upgrade a failed
command to success. It runs only at the module entry points, leaving streams
owned by direct `main()` callers alone. No file redirection, process-wide signal
change, retry loop, extra output field or qualification threshold is introduced.
The two golden positive/negative report formats remain unchanged.

Tests create an anonymous pipe and close its read end before launching the
child. This gives a deterministic kernel write failure without sleeps, hardware
or timing assumptions. Every child has a ten-second timeout and a fixed module
argument list, with no shell. Python's `-E` isolates the test from Python-specific
environment options such as unbuffered output. It is not a sandbox claim.

## Technology reassessment

The deployed boundary remains a synchronous source-checkout command calling
bounded immutable-byte APIs, emitting one minimized JSON report. Constraints are
exact bytes, checked write/flush/exit behavior, no new transport representation,
and preservation of caller stream ownership. There is no native ABI, standalone
installer, service supervision or hard deadline requirement for this component.

| Candidate | Requirements-based assessment |
|---|---|
| Python argparse/struct plus explicit stream finalization | Invokes the existing byte APIs directly and controls their actual interpreter exit path. The new kernel-pipe tests exercise the previously unverified behavior. |
| Rust clap and fallible output | Credible native command parsing and output handling. A binding or complete validator implementation still needs exact byte/report/error parity; native ownership does not establish delivery acknowledgement. |
| Go binary/I/O command | Explicit close-error reporting and fixed-width decoding suit a standalone native consumer. No required native packaging or measured resource deficit currently selects that boundary. |
| Erlang bit syntax and a supervised process | Binary matching is suitable for framed bytes and supervision for services. A separate VM/process protocol adds a new boundary to this one-shot API; supervision cannot itself prove consumer receipt. |

Primary sources checked:
[Python exit and cleanup status](https://docs.python.org/3.13/library/sys.html#sys.exit),
[Python I/O close](https://docs.python.org/3.13/library/io.html#io.IOBase.close),
[argparse](https://docs.python.org/3.13/library/argparse.html),
[Rust clap](https://docs.rs/clap/latest/clap/),
[Go file close](https://pkg.go.dev/os#File.Close), and
[Erlang bit syntax](https://www.erlang.org/doc/system/bit_syntax.html).
A .NET Stream.Close page fetch failed; no capability or exclusion is inferred
from that unavailable source. The earlier broader review remains discovery input.

**KEEP Python commands; FIX process-owned stream finalization.** Direct byte/API
composition and demonstrated control of this exit boundary are the decisive
properties. No native runtime advantage was measured; familiarity, installed
tools and rewrite cost are not reasons for the decision. Reopen for a native ABI,
installed distribution, service-delivery contract or measured target constraint.

## Evidence and limits

[Retained evidence](cli-shutdown-review-v3.json) records four initial assertion
failures, zero execution errors, 12 passing CLI/report methods and 28 passing
reference/bundle/integration methods. Ruff and formatting pass. Production Bandit
checks have zero findings; the new process test retains two low findings (B404,
B603) for its reviewed fixed-argument, timeout-bounded subprocess call. Nothing
is suppressed. Local execution is Linux CPython 3.13.5; hosted Python 3.9 and other
platform behavior are not claimed from these results.

Partial output cannot be retracted; consumers must require the appropriate exit
status and complete JSON. Writable stderr remains necessary. Close/flush may
block, so supervisors still own deadlines. This correction is not delivery
acknowledgement, storage durability, authentication, installed-product acceptance,
availability or physical qualification. Insufficient information for tactical
deployment. P15/P19 procedure and product acceptance software remains incomplete;
the next review boundary is portable consumer evidence and the remaining audit
tooling/hosted verification configuration. No audit-complete marker is justified.
