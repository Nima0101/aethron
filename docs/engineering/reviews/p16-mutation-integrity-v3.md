# P16 mutation evidence integrity review v3

Baseline: `eb324cb2ba0def30766c52c1b77d424dfcdf2759`. Reviewed 2026-10-10.
Decision: **KEEP bounded in-process mutation tests; FIX source consistency and baseline
admission**. The timing bridge was verified against its parent, six recorded file hashes
and noreply identity. The earliest passport parser, trust and evidence implementations
were re-read; this slice corrects assurance tooling without changing admission behavior.

## Constraints and technology reassessment

The driver runs four predeclared guard-removal experiments against trusted local Python
source and selected unittest methods. It must report only experiments whose unchanged
baseline passes, preserve original module bindings on failure, and reject visible file
changes during execution. It is a sequential developer diagnostic, not a concurrent
service, arbitrary-code sandbox, comprehensive mutation score or physical test harness.

| Candidate | Evidence and decision |
|---|---|
| Captured bytes plus scoped Python module substitution | [Path.read_bytes](https://docs.python.org/3.13/library/pathlib.html#pathlib.Path.read_bytes) supplies explicit bytes; [patch contexts](https://docs.python.org/3.13/library/unittest.mock.html#patch-dict) restore replaced bindings. KEEP: directly exercises the selected Python guard changes and their actual tests without a second protocol or generated mutation inventory. Add baseline and final byte-equality gates. |
| mutmut | The [project documentation](https://mutmut.readthedocs.io/en/latest/) describes automatic Python mutation testing and process isolation using fork or forkserver. Suitable for broader mutation discovery; that is a different experiment from these four named guard removals. No tool installation, broad mutation run or comparative throughput claim here. |
| Java/JVM PIT | [PIT](https://pitest.org/) provides mutation testing for Java/JVM code, a credible ecosystem beyond the component's language. It would exercise a JVM implementation, not these Python function bodies. No JVM admission implementation or semantic-parity evidence justifies that replacement. |
| Per-experiment isolated Python processes | A candidate when independently isolated global state or hostile test code is required. This driver assumes trusted single-threaded tests and restores its two patched bindings; it does not promise process isolation. Additional processes alone would not bind source bytes or establish a passing baseline. |

This choice follows the exact experiment and source-language boundary, not tool
availability or rewrite cost. No runtime speed ranking was performed. Captured-source
compilation and the corrected controls are executable evidence for this bounded choice.

## Two reproduced false-success paths

The runner previously loaded passport source as text, then hashed files after execution.
A persistent change during testing could be included in an apparently successful report.
One new test simulates a changed final read for each of the five listed paths; all five
cases initially failed the required rejection assertion, with zero execution errors.
The implementation now captures bytes before testing, compiles mutations from that
captured UTF-8 passport source, compares final reads, and raises
`mutation_source_changed` before JSON output if any listed file differs. Digests describe
the retained bytes. Tests simulate changes without rewriting production files.

The runner also previously credited assertion failures without first proving the selected
tests passed on unchanged code. Replacing one selected test with an unconditional fixture
failure demonstrated a second false success. Its regression initially failed once with
zero execution errors. The runner now executes all four selected methods against an
unmodified module compiled from the captured source. Failure, error, skip, expected
failure, unexpected success or an incomplete method count rejects the baseline. Only
then are the four modified modules tested. Successful output adds `baseline_tests`.

A shared private runner scopes both baseline and mutant substitutions. A separate
control injects RuntimeError and KeyboardInterrupt during the scoped run, verifies that
the original test verifier and pre-existing module-table entry are restored, and checks
that no JSON is emitted. That control already passed before refactoring; cleanup was
confirmed correct, not reported as a newly discovered defect. A successful control checks
four baseline methods, the four named guards and eight expected assertion failures.

## Evidence and limits

The related passport/evidence/schema/probe suite passed 68 methods with zero skips.
The live isolated-mode CLI report passed four baseline methods and detected all four
mutations (eight expected assertion failures). Lint and security scanning passed;
format checking initially required a test-only formatting correction. Security scanning
excludes B101/B102 for the explicit guarded assertions and trusted-source in-memory exec.

The first policy read and several process launches failed from host resource exhaustion;
the required read subsequently succeeded. A prior-commit push also failed when its
credential helper could not create a thread. These are infrastructure failures, not
passing delivery evidence. No sandbox override or peer-process intervention was used.

Before/after reads are not an atomic snapshot: restored transient changes, preloaded
module divergence, changes after the final read and unlisted dependencies remain outside
the check. Loaded tests/helpers are not attested; fixed trusted paths have no new file-size
bound. Only the two patched bindings are restored, not arbitrary test side effects.
A passing baseline plus mutant assertion failures establishes these experiments, not
causal completeness, cryptographic certification or overall security coverage. Historical
results remain unchanged. No physical, MLS, CNSA or availability qualification is implied.

[Source-bound results](p16-mutation-integrity-v3-results.json) retain the negative tests,
verification outcomes, log digests and live report. P16/P17/P18 remain incomplete. Next:
reconcile the built-component inventory and remaining transport/cross-phase contracts
against protected main. Insufficient information for tactical deployment.
