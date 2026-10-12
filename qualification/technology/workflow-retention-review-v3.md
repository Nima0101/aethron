# Hosted experiment retention review

Baseline: `79ff2942253cbc107e7b79e5efb67474673b7491`. The fresh P4/P15 review
rechecked the earliest declaration/campaign contracts, CLI delivery and false
qualification flags, then examined the hosted ingress experiment's output boundary.
Its upload selected only `*.json`. Generated `requests.hex` and `responses.jsonl`
were omitted, so a retained comparison did not include the raw transport needed
to reproduce or inspect a failed comparison. Compiler/runtime versions and the
compiled class fingerprint were also absent from the artifact.

The workflow now records the actual checkout SHA, Java/compiler/Python/Node
versions, and source/parser/class SHA-256 observations. Source and parser files
are checked after compilation; all three observations are checked before and
after the Java request batch. Failures stop the step. The upload retains raw
requests/responses, the existing reports and the named metadata files even when
earlier steps fail. It does not upload the Jar, class binary or whole temporary
directory. Partial and missing files still mean incomplete evidence, never PASS.
Seven-day retention and missing-file warnings remain explicit; this is diagnostic
retention, not a permanent release evidence archive or completeness validator.

## Technology reassessment

The component runs in an Ubuntu GitHub Actions job with fixed trusted file names,
bounded synthetic requests and an already-pinned parser. It needs raw artifact
retention and direct observations around existing shell commands. It is not a
product runtime, credential service, package signer or hardware qualification path.
GitHub is not introduced as a requirement for offline product deployment.

| Candidate | Decisive fit and limitation |
|---|---|
| GitHub Actions paths plus shell checksum checks | Attaches the selected files directly to the producing job and exposes command failures without another report process. Paths are fixed and quoted. |
| Python or Node archive collector | Can build an archive, but a second file-selection implementation is unnecessary for fixed paths already supported by the uploader. It would not make experiment results authentic. |
| F# or C#/.NET ZipFile collector | Credible archive APIs for independent packaging; creating a second archive does not improve the required job association or missing-file visibility here. |
| Nix derivation/build closure | Relevant to controlled build inputs and reproducibility, a stronger and separate requirement than retaining this experiment's outputs. Metadata cannot substitute for such a build. |

**KEEP the native workflow mechanism; FIX its selected files and observations.**
The decision follows the required job/file boundary, not installed tooling,
language familiarity or rewrite cost. Reopen for durable release archives,
hermetic builds or independently verified execution attestations.
Primary sources: the
[pinned uploader documentation](https://github.com/actions/upload-artifact/blob/ea165f8d65b6e75b540449e92b4886f43607fa02/README.md),
[workflow artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data),
[.NET ZipFile](https://learn.microsoft.com/en-us/dotnet/api/system.io.compression.zipfile?view=net-9.0),
and [Nix derivations](https://nix.dev/manual/nix/2.34/language/derivations.html).
Suitability is the analysis above; no unmeasured performance ranking is inferred.

## Reproduction and limits

For an artifact from a successful run, check out its recorded `checkout.txt` SHA,
check `source.sha256` from that checkout, reacquire the parser from the pinned
workflow URL and verify `parser.sha256` in the artifact directory. Recompile with
the recorded compiler and workflow flags and compare `compiled.sha256`; different
toolchains may produce different class bytes. Run the recorded requests with that
classpath and require successful exit before comparing the response transport and
running `compare_ingress --responses`. This procedure does not authenticate the
artifact or claim a bit-identical runtime installation.

The bounded selection fixture initially reported ten missing files; after the
change it selects all fifteen expected files and excludes the Jar, class binary
and an unrelated file. This local glob check is not a hosted upload test. Three
actual YAML command blocks are executed locally: metadata, compilation and the
81-request comparison. Changed parser/class bytes and a missing class must fail
before Java response/comparison creation. Actionlint checks the configured YAML.
Results and source bindings are retained in
[workflow-retention-review-v3.json](workflow-retention-review-v3.json).
Local results describe the modified working-copy workflow over the baseline;
the recorded checkout SHA alone does not bind those edits. The result separately
records the exact workflow digest.

The first local command-block attempt failed because bare `python` was absent
from PATH. The retry prepends the existing qualification tooling environment,
matching the name supplied by hosted setup-python. This setup failure is retained,
not counted as a negative-control success. Local Java is JDK 21; the configured
hosted Java 17 result remains unestablished. A main fetch was denied by read-only
FETCH_HEAD; cached main is not represented as a fresh remote snapshot.

File checks are non-atomic observations: transient reverted changes, malicious
tools, unlisted dependencies and post-check edits remain outside their guarantees.
The source/compiled fingerprints do not prove which code executed. Version text
is self-reported tool metadata, not a complete dependency inventory. Historical
records remain unchanged. No hardware, customer-acceptance or cryptographic
certification is claimed. Insufficient information for tactical deployment.
