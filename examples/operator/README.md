# P12 observation presentation components

The presenter maps an SDK aggregate view to fixed English (`en`) or Swedish
(`sv-SE`) text. The reusable DOM panel adds language buttons and contextual
Help/Hjälp disclosure for expired, delayed and invalid observations. All current
conditions remain `UNKNOWN`; an earlier `PRESENT` observation is labelled as
historical. Invalid input withdraws sensor details. This is not a complete operator
application or a qualified browser distribution.

Prepare locked development dependencies once, then run the focused checks:

```sh
npm ci --prefix examples/clients/typescript --ignore-scripts
npm ci --prefix examples/operator --ignore-scripts
npm test --prefix examples/operator
```

Preparation needs a registry or a populated offline npm cache. Tests compile the
SDK and panel, then exercise the presenter and a structural DOM implementation.
The panel has no runtime library dependency. LinkeDOM is development-only; it does
not verify browser layout, keyboard behavior or screen-reader output.

A host with an existing admitted SDK `observation` can mount the built module:

```js
import {mountObservationPanel} from './dist/panel.js';
const panel = mountObservationPanel(root, () => observation.view(), 'en');
// Call after admission, on the host's expiry watchdog, and on host activation:
panel.refresh();
// Before removing the host view or logging out:
panel.dispose();
```

The host must own `root` exclusively, retain the SDK observation, enforce source
access/authorization and schedule refreshes. This component never connects to a
service or starts a timer. Every refresh, language change and opening of help calls
the reader again. Never supply a cached projection as a freshness guarantee.
Stalled host execution can leave delayed historical text visible; the displayed
current conditions remain UNKNOWN. Disposal removes listeners and owned content,
clears the panel's text nodes, and makes later controller calls inert. It cannot
erase strings another caller copied earlier or close a host transport session.

The panel updates existing controls without replacing them on refresh. Content
uses text nodes; status has polite/atomic live-region attributes. Those semantics
still require real-browser keyboard/focus and assistive-technology acceptance.
Unsupported locales throw `unsupported_locale` before changing the view. Reader
exceptions become fixed invalid guidance without including exception text.

`presentObservation(observation.view(), locale)` remains available independently.
It snapshots before validation; direct object admission has no pre-clone allocation
bound. Use bounded SDK wire ingress for network data. Sensor names are vocabulary,
not source authentication or calibration evidence. Raw covariance/geometry,
track/session IDs and caller input are not returned or rendered.

The three local topic IDs are `observation.expired`, `observation.delayed` and
`observation.invalid`. Their disclosure content follows the current displayed
state and locale. No role-sensitive administrator guidance is included. Search,
role enforcement, onboarding, release-SHA-bound bidirectional help coverage,
scene/map/replay flows and integrated P19 acceptance remain unfinished. Two local
Chromium probes timed out; no browser acceptance is claimed. No hardware, tactical,
availability or security certification follows from these tests.

See the presenter [ADR](adr.json) and [schema](adr.schema.json), panel
[ADR](panel-adr.json) and [schema](panel-adr.schema.json), and
[panel implementation plan](RENDERER-PLAN.md).
