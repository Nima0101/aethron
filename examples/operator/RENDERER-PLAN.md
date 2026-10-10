# P12 observation panel implementation plan

Execution: inline, no subagents, under the owner's autonomous implementation order.
Use writing-plans/executing-plans and TDD; scoped checks only. No extra approval gate.

Goal: Render the existing aggregate presenter in a reusable offline DOM panel with
native language buttons and contextual disclosure help. The host owns transport,
refresh scheduling and authorization. This component does not start a session.

Design: `mountObservationPanel(root, readView, locale)` returns `refresh()`,
`setLocale(locale)` and `dispose()`. Mount, refresh, locale changes and opening help
request a fresh host view. Reader exceptions yield the invalid/UNKNOWN presenter.
Keep nodes stable across updates so controls and disclosure state survive refresh.
Use only textContent for display content, native buttons/details/summary, section
lang and a polite atomic status. Dispose removes listeners/content and prevents
late callbacks from restoring data. The host must provide an exclusively owned root.

Technology: TypeScript with native DOM, no runtime dependency, template compiler
or bundler. Lit offers reactive custom elements; Elm ports offer explicit message
flow; ReScript offers typed JS interop. None removes the host validation/freshness
boundary for this small fixed panel. LinkeDOM 0.18.13 is a locked development-only
structural DOM test dependency; it cannot establish browser accessibility/layout.
Sources: https://dom.spec.whatwg.org/#dom-node-textcontent,
https://html.spec.whatwg.org/multipage/interactive-elements.html#the-details-element,
https://lit.dev/docs/, https://guide.elm-lang.org/interop/,
https://rescript-lang.org/docs/manual/latest/json,
https://github.com/WebReflection/linkedom.

Review focus: expiry on language/help interactions; read exceptions; markup inputs;
late calls after disposal; stable controls. No role controls or hidden admin help.

- [x] Write DOM regression tests; observe missing renderer RED.
- [x] Implement src/panel.ts with the interface and lifetime above.
- [x] Run presenter plus panel tests, compiler, dependency audit and workflow lint.
- [x] Record closed ADR/C4, evidence/limitations and CI dependency preparation.
- [x] Self-review and bridge commit (`1e99e94`); re-entry correction (`c6db2d6`), both published to PR #44.

Actual browser keyboard/focus/screen-reader and customer-installed acceptance remain
required. Two bounded Chromium probes timed out in this sandbox; no security flags
will be disabled to produce a passing claim. P19 Help Center/search/roles, release
inventory and integrated application remain unfinished.

Initial panel verification: 8 assertion failures became 8 passes. Two additional retained-node/getter-disposal failures were corrected. The original combined presenter/panel run had 28 PASS, no skips. That checkpoint's dependency audit reported zero known vulnerabilities and workflow actionlint passed. Subsequent re-entry and lifecycle results are recorded in P33-REVIEW-V3.md; browser acceptance remains unexecuted.

Self-review correction: unchanged refresh now preserves text nodes while re-reading the host. The original DOM identity assertion exhausted the test formatter heap; retained as negative evidence. Boolean identity assertion avoids recursive DOM formatting, and the original unconditional assignment is reproduced in an isolated test copy. No threshold or memory cap was raised.
