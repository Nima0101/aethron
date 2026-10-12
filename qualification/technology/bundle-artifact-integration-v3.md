# Bundle and artifact consumer review — 2026-10-10

Baseline: `bcb9b2fa455ef79c43a173ce93975fa792277711`. The review restarted
with declaration admission/calibration/clock/environment, artifact byte binding,
campaign coverage, reference binding and bundle/stream consumption. The existing
versioned semantics remain consistent: all are bounded offline checks over
caller-supplied inputs, with no instrument authentication, trusted clock sampling,
device access or physical qualification. No new production defect was demonstrated.
The correction adds missing composed-API evidence and explicit consumer guidance.
It changes no frozen threshold, protocol, schema, report field or production code.

## Constraints and technology decision

The immediate requirement is a small deterministic regression suite over the real
synchronous APIs and one real module subprocess. It must preserve exact immutable
bytes, caller-supplied instants, separate negative reports and process exit status.
It must not invent a new acceptance service, artifact transport or hardware source.
This is neither an installed-product test nor a performance benchmark.

| Candidate | Decisive fit and limitation |
|---|---|
| Python `unittest` | Direct calls observe the actual typed byte APIs without introducing another encoding boundary; assertions and process checks cover the required outputs. |
| Robot Framework with Python libraries | Credible keyword-based acceptance suites with reusable libraries. Here custom keywords would wrap the same small byte API without exercising an additional shipped interface. Revisit for operator-facing acceptance workflows. |
| F# with NUnit/.NET | Credible typed test fixtures and assertions. A separate host can independently test published wire contracts, but the artifact checker currently has no process or network interface. Such a test would introduce an unshipped bridge or test a second implementation. |
| Erlang Common Test | Credible distributed/black-box protocol testing and logging. No distributed target or concurrent connection management is required for this finite local API composition. |

**KEEP direct Python tests for this component.** This is a boundary-fidelity
decision, not a preference based on installation, familiarity or rewrite cost.
The language choices of the validators remain subject to their separate
component reviews; a test harness is not evidence that those languages win
universally. Published native/wire interfaces, independent installed-product
acceptance or a measured resource constraint reopen this choice. No alternative
runtime benchmark or prototype was run for this test-only correction.

Primary sources inspected: [unittest fixtures/assertions](https://docs.python.org/3.13/library/unittest.html),
[Robot Framework libraries](https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html),
[F# NUnit tests](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-fsharp-with-nunit),
and [Common Test targets and suites](https://www.erlang.org/doc/apps/common_test/basics_chapter.html).
These sources describe mechanisms; the selection is this review's judgment.

## Executable coverage and limits

Four new methods use the actual bundle/artifact APIs without mocks:

- All four fresh/stale and matching/altered artifact combinations keep byte
  verification separate from declaration validity. The same manifest digest can
  accompany different freshness results; the campaign commitment changes with time.
- A previously passing artifact report does not bind a substituted manifest with
  expired calibration, even when its artifact references are identical. Rechecking
  the changed bytes retains the calibration failure in both APIs.
- Each reused capture can pass artifact checks individually while the campaign
  rejects both occurrences, including when evaluation instants differ.
- A real stdin/stdout subprocess preserves expired calibration, stale capture,
  clock-domain mismatch and both reference mismatches. The separate artifact API
  retains missing, altered and extra bytes alongside those declaration failures.
  Original manifest whitespace is retained. Synthetic private markers are omitted
  from both reports, which still contain linkable digests/counts.

All authority/physical flags remain false, including when software checks pass.
This suite does not implement a production aggregate acceptance gate or authenticate
returned reports. It cannot establish actual source authorization, sensor quality,
independent acquisitions, complete submission, a trustworthy evaluation instant,
installed release/help coverage, target latency, uptime or certification.

The new four methods passed on first execution. There is **no production RED/fix
claim**. The combined eight-module focused run passed 63 methods with no failures,
errors or skips. Results and post-run source-file observations are retained in
[bundle-artifact-integration-v3.json](bundle-artifact-integration-v3.json). Existing
CI discovery includes the new file; hosted success has not been observed.

Ruff and formatting passed. A direct Bandit scan of the new test returned two low
findings, B404 and B603. Review confirms a fixed `sys.executable`/module argument
list, default `shell=False`, a checkout-derived working directory, a ten-second
timeout and synthetic input carried only on stdin. Neither command nor cwd is
derived from the manifest. Findings are retained, not suppressed or represented
as a clean test-file scan. This reasoning assumes a trusted interpreter/checkout;
it does not establish security of arbitrary Python startup environments.

Reproduce the new methods with:

```sh
python3 -m unittest qualification.tests.test_bundle_artifact_integration -v
```

This evidence supports reusable non-actuating qualification checks only. Actual
source-authentication contracts, target-device observations and installed-product
acceptance inputs remain separate integration gates. No lane or technology-audit
completion marker is created by this review.
