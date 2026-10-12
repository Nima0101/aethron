# Qualification report delivery review — 2026-10-10

Baseline: `8534a2475c2119855ae0b151913d661ff119f49a`. The tracing bridge
was verified against its seven recorded paths and noreply identity. The current
policy and earliest declaration, artifact, campaign, reference, bundle and CLI
boundaries were reread; 97 focused methods passed. No new admission defect or
required migration was demonstrated in that baseline. Their bounded offline
constraints and the component comparisons in [review-v3.md](review-v3.md) remain
applicable; this record addresses the subsequent delivery verification gap.

## Findings and corrections

**FIX workflow dependency triggers.** Importing `aethron._json_bounds` first runs
`aethron/__init__.py`, which imports `core`, then `actions`, `features` and `schema`.
The workflow previously watched only `_json_bounds.py`. It also omitted
`pyproject.toml`, which supplies Ruff configuration. The retained RED control found
six uncovered paths in each of the two event filters. Both now watch `aethron/**`
and `pyproject.toml`, in addition to existing qualification, development-requirement
and workflow paths. Watching the package conservatively covers future transitive
imports; it does not change or take ownership of peer code. This job uses a source
checkout, not a built wheel, and no installed-package verification is claimed.

**FIX process-boundary test coverage.** Existing bundle tests called `main()` with
in-memory streams. Four new methods invoke the real module in a child interpreter
using byte pipes: exact frozen success output twice, simultaneous reference and
coverage failures with exit 1, malformed input with exit 2, and a private synthetic
argument with fixed stderr and empty stdout. No stdout/stderr normalization is used.
The existing test discovery step runs these controls on each configured Python
version. Disabling the module entry guard must fail all four methods; restoration
must pass. The runtime admission implementation and versioned frame are unchanged.

## Requirements and technology reassessment

The test needs the same interpreter selected by the hosted matrix, exact binary
stdin/stdout, separate stderr, explicit nonzero exit checks, and a finite wait for
the known repository child. It has no native distribution, interactive terminal,
remote execution or hard real-time requirement.

| Candidate | Decisive properties |
|---|---|
| Python `subprocess.run` and `unittest` | Directly selects `sys.executable`; preserves byte pipes and return codes; integrates explicit assertions into the existing matrix. No shell quoting or JSON wrapper is needed. |
| Node `spawnSync` / test runner | Has explicit process arguments, output buffering controls and timeout options. A viable independent command harness; still needs the selected Python executable and byte framing. Its output cap could matter for testing an untrusted executable, which this is not. |
| C#/F# `Process` with `ArgumentList` | Typed arguments support a credible non-incumbent host. Separate stream draining, interpreter selection and timeout cleanup still need explicit implementation. No .NET host integration requirement favors that extra execution boundary here. |
| Shell pipeline and byte comparison | Suitable for fixed redirected files, but expected failure statuses and binary input construction require separate handling. Structured assertions make the multiple independent outcome checks easier to inspect. |
| Native GitHub workflow YAML | Required by the selected hosted platform. Keep the explicit event filters and source discovery step; a generator would add a second configuration boundary without a present requirement. |

**KEEP native workflow YAML; SELECT Python byte-mode process tests.** This selects
the interpreter under test explicitly and checks the actual public command without
an extra transport serialization. It is not a speed ranking, incumbent preference
or claim that other hosts cannot implement the contract. Reopen if an independently
distributed native executable, untrusted-child resource containment or a different
hosted platform becomes a requirement.

Primary sources inspected for mechanism semantics:
[Python subprocess](https://docs.python.org/3.13/library/subprocess.html),
[Node child processes](https://nodejs.org/api/child_process.html),
[.NET ArgumentList](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.processstartinfo.argumentlist?view=net-9.0),
and [GitHub workflow path filters](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
The candidate suitability judgments are this review's analysis. A GNU Bash manual
fetch failed; no source-backed comparison claim is inferred from that failure.

## Evidence and limits

The ten-second subprocess timeout is test supervision, not a production deadline:
process creation itself may outlast it. Output capture uses memory and has no
independent byte cap. The child is trusted repository code exercised with small
synthetic fixtures; this is not containment for arbitrary executables or hostile
output. The tests inherit the host environment and do not attest interpreter,
operating-system or dependency authenticity. They run from the source checkout.

[delivery-review-v3.json](delivery-review-v3.json) retains RED trigger controls,
module-entry mutation failures, restored test results and listed source hashes.
Local Python execution and actionlint do not establish hosted execution, all
supported Python versions, packaging or hardware qualification. Hashes and reports
grant no motion authority, instrument authenticity, domain/procedure approval,
physical capability or security certification. Physical qualification stays false.
