# Comparison result admission review v3

Baseline: `8c9f5834f110d719a69d3949e1222cbab3703d52`. The current policy and V3
order were reread. The six-file review-result bridge commit and noreply identity
were verified; its immutable-tree link check passed and the commit was pushed.
The single PR observation still contained pending checks. No merge is claimed.

The walk revisited declaration fixtures, artifact/reference/bundle boundaries,
the three review drivers, and then ingress collection and SQL comparison.
Fixture builders are code in the already-bound test modules. A fresh inventory
matched all 251 declared source bindings in 22 retained reports to their publication
commits. This includes nested source maps; report hashes and immutable locators
are retained in [comparison-results-v3.json](comparison-results-v3.json).
Source equality proves neither execution nor completeness of the dependency list.
Historical reports are unchanged and are not upgraded to current-source results.

## Requirements and technology reassessment

These finite source-checkout tools collect Python validator calls, compare an
audit candidate and preserve assertion failures separately from execution errors.
They need scoped function instrumentation and structured result categories.
There is no device interface, hard deadline, native ABI or distributed scheduling
requirement. Timings remain descriptive shared-host observations.

| Candidate | Decisive properties for this boundary |
|---|---|
| Python unittest with checked result categories | Directly exposes test counts, skips, assertions, errors and expected/unexpected outcomes beside the instrumented Python calls. |
| pytest | Has an explicit no-tests exit category; adopting that runner still needs structured mutation outcomes and candidate-call evidence. |
| C#/F# Microsoft.Testing.Platform | Offers no-tests/minimum-test outcome categories. The Python calls and scoped substitutions require a checked bridge or a separate semantic implementation. |
| Process coordinator with structured reports | Can isolate candidate failures; process exit alone cannot prove that semantic cases or candidate calls executed. A separate result transport would be required. |

**KEEP Python direct orchestration; FIX evidence admission.** The decisive fit is
access to the actual tested call and its structured outcome without an additional
representation boundary. No installation, familiarity, rewrite-cost or measured
speed argument is used. Process isolation or a native consumer would reopen this
choice. Sources consulted: [unittest result API](https://docs.python.org/3.13/library/unittest.html#unittest.TestResult),
[pytest exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html),
and [Microsoft.Testing.Platform outcomes](https://learn.microsoft.com/en-us/dotnet/core/testing/microsoft-testing-platform-troubleshooting).
Selection is this review's inference from the component requirements.

## Correction and evidence

Ingress collection accepted successful empty/skipped/expected-failure results.
SQL comparison had the same baseline gap, could report zero candidate calls,
and treated an unexpected success as mutation detection. The earlier correction
to the three review drivers did not cover these separate comparison tools.

Both baselines now require nonempty successful execution without skips or expected
failures. Ingress requires collected requests; SQL comparison requires observed
candidate calls. SQL mutation detection requires assertion failures without
errors, skips, expected failures or unexpected successes. Failed admission emits
no comparison report. Existing report keys, transport bytes and production
qualification gates remain unchanged.

Four new methods cover twelve negative combinations and actual collection/SQL
execution. RED produced eleven assertion failures and zero errors. Twenty-two
focused methods then passed. Ruff found two unbound loop callback captures in the
test; binding those values explicitly resolved the findings, and the four new
methods were rerun. Formatting, targeted Bandit and Python 3.9 syntax also pass.
The existing hosted test discovery includes the new file without workflow edits.

No Java execution is inferred from Python collection tests. SQL aggregation still
shares admission and declaration semantics with Python. Nonempty execution is not
proof of complete discovery or scientific sample independence. The remaining
P15 producer/procedure integration review is open; hardware qualification stays
external and no audit-complete marker is created.
