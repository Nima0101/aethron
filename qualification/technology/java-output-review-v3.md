# Java experiment output delivery review

Baseline: `abd692acfb1f41275f3e983c78cb0acc1459c636`. The fresh P4/P15 walk
reread declaration admission, artifact binding, campaign coverage, reference
binding and bundle composition before reviewing the Java probe and its hosted
workflow. Those APIs retain bounded immutable inputs, independent negative
findings and false physical/authenticity approval flags. This slice corrects an
executable mismatch in the Java experiment; it does not complete lane review.

## Defect and correction

`System.out.println` used the default output encoding and ignored the stream's
error state. A full output sink produced exit zero for both accepted and rejected
requests. Under an ASCII output encoding, an accepted document containing
`Ångström` became `?ngstr?m`. This violated response delivery and document fidelity.
Historical results remain unchanged; they do not prove behavior under these
failure conditions or alternate encodings.

The probe now constructs each response, encodes it explicitly as UTF-8 with one
LF terminator, writes bytes, and calls `checkError`. That operation flushes and
observes the PrintStream error flag. A failure throws `IOException` with
`probe_output_unavailable` outside the input-rejection catch. Transport failure
cannot become an ordinary `accepted:false` response. Previously emitted bytes
cannot be revoked: callers must require successful process exit and complete
response comparison before using any output. Flush is not a durability guarantee.

Input caps, duplicate detection, token rules, row accounting and the shared Python
semantic oracle are unchanged. This is still a trusted synthetic audit transport,
not a private-error service or an independent Java qualification implementation.

## Technology reassessment

Constraints are Java 17-compatible code exercising Jackson, at most 256 rows and
8 MiB of transport, UTF-8 JSON response fidelity, bounded decoded documents and
observable process delivery failure. No native ABI, physical device, persistent
store, target memory ceiling or real-time deadline is established. Current local
execution uses JDK 21; compiling with `--release 17` is not Java 17 runtime testing.

| Candidate | Decisive fit and limitation |
|---|---|
| Java PrintStream byte writes plus explicit error check | Preserves the tested parser/runtime and observes its actual stdout failure state; explicit bytes avoid default charset conversion. |
| Java OutputStreamWriter / BufferedWriter | Supports explicit text encoding. Wrapping System.out still inherits its suppressed exceptions unless its error state is checked; owning a separate descriptor changes the output ownership boundary. |
| F# or C#/.NET StreamWriter coordinator | Credible encoded stream output, but would add another process boundary while the Java producer could still silently lose or corrupt data. Replacing Jackson would test a different parser. |
| Python byte-stream supervisor | Can reject missing rows and unsuccessful children, as the existing comparator does. It cannot make a zero-exit Java producer accurately report its own delivery state; the producer still needs correction. |

**KEEP Java for the Jackson experiment; FIX output handling.** The choice follows
the experimental subject and ownership of the failing stream. It is not a
production runtime ranking, installation preference or rewrite-cost argument.
Reopen the production-language question for a concrete deployment or measured
resource requirement. Primary mechanism sources are the
[Java 17 PrintStream contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html),
[Java output streams](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html),
and [.NET StreamWriter](https://learn.microsoft.com/en-us/dotnet/api/system.io.streamwriter?view=net-9.0).
The component suitability conclusion is this review's analysis.

## Verification and provenance limits

Two added real-process regression methods exercise `/dev/full` with accepted and
rejected inputs and force ASCII output defaults with non-ASCII JSON. Together
with six existing framing methods, the baseline produced three assertion failures
and zero execution errors. After correction all eight methods pass. These optional
tests require Linux and a compiled classpath and do not silently skip. The existing
Ubuntu audit job already invokes the whole test module.
Thirteen focused declaration, artifact and campaign review methods also pass,
including independent negative findings and the limits of byte commitments.

Fresh compilation uses the workflow-pinned Jackson digest, `--release 17`,
`-Xlint:all` and `-Werror`. The 81-request Java run retains document and semantic
report parity. The raw comparison, compiled class and Jar fingerprints, source
bindings and local tool versions are recorded in
[java-output-review-v3.json](java-output-review-v3.json). The local compiled
artifact is not claimed to be identical to a hosted build. Source, class and Jar
digests are locators, not authenticated execution or supply-chain attestations.

The workflow checks its downloaded Jar against a pin and compiles the checkout;
its retained JSON comparisons do not alone establish a complete authenticated
runtime/dependency closure. Hosted checks were queued at the published baseline,
so no hosted PASS is claimed. The local JDK differs from the hosted Java 17 target.
No hardware, installed-product, cryptographic-certification or hard-real-time
qualification follows. Insufficient information for tactical deployment.
