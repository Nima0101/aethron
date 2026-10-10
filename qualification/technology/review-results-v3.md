# Review result admission v3

Baseline: `0f7bc5ed1773a294436bcbe5929997884fa6fe9f`. The policy and V3 order
were reread. The declaration and artifact implementations and the declaration,
artifact and campaign negative controls were inspected again. The previous
report-output bridge commit was verified, its immutable-tree links passed, and
it was pushed. CI was pending at the single observation; no merge is claimed.

## Constraints and technology decision

These synchronous offline drivers exercise bounded synthetic Python API calls,
temporarily patch selected functions, distinguish assertions from execution
errors, restore the patched state and emit JSON. They need result categories and
direct access to the functions under review, not a device ABI, distributed service,
hard deadline or persistent store. The hosted contract remains Python 3.9/3.13.

| Candidate | Decisive property |
|---|---|
| Python unittest with explicit result checks | Exposes counts, skips, failures, errors and expected/unexpected outcomes directly beside the tested API and scoped patches. |
| pytest | Provides a distinct no-tests exit code and supports a broader runner ecosystem; exit status alone is still insufficient evidence of the required mutation assertion categories. |
| C#/F# with Microsoft.Testing.Platform | Provides explicit no-tests and minimum-test exit categories. Exercising these Python function substitutions requires a checked adapter or a separate semantic implementation. |
| A shell subprocess coordinator | Provides process isolation, but process status alone loses the result distinctions needed here unless a structured result protocol is added. |

**KEEP Python unittest; FIX result admission.** Direct typed result access and
scoped function replacement satisfy this component's requirements without a
second result transport. This is a semantic fit, not a familiarity, installed-tool
or rewrite-cost preference. No relative performance claim was measured or needed.
Reassess for independent process isolation or native runtime consumers.

Primary sources inspected: [unittest results](https://docs.python.org/3/library/unittest.html#unittest.TestResult),
[pytest exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html),
and [Microsoft.Testing.Platform outcomes](https://learn.microsoft.com/en-us/dotnet/core/testing/microsoft-testing-platform-troubleshooting).
The candidate suitability judgments are this review's inference.

## Defect and executable correction

An empty suite is successful under unittest. Skips and expected failures can also
coexist with a successful result. Declaration/artifact drivers accepted those
baselines; the campaign driver rejected skips but accepted emptiness and expected
failures. All three could misclassify an unexpected success as a killed mutation,
because a non-successful result with no errors need not contain an assertion failure.

Baseline and restored runs now require a nonempty successful result without skips
or expected failures. Mutations require at least one assertion failure, with no
errors, skips, expected failures or unexpected successes. Rejection precedes report
emission. Existing report fields and all qualification thresholds are unchanged.

Four new test methods use real unittest results for 33 negative combinations and
execute the actual three drivers as positive controls. Before correction there
were 27 assertion failures and zero errors. The corrected tests and 19 adjacent
methods pass. The existing ten semantic mutants remain detected after restoration.
The hosted workflow already discovers the new test file; no workflow edit is needed.

These checks do not prove full test discovery, independent oracle correctness,
authenticated evidence, or hardware qualification. They reject the enumerated
incomplete/ambiguous outcomes. Historical result files remain unchanged; their
source versions must still accompany their claims. Current evidence and source
bindings are in [review-results-v3.json](review-results-v3.json). The wider P4/P15
source inventory and producer integration review remain open; no completion marker
or physical qualification claim is created.
