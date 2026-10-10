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

`npm run build --prefix examples/operator` removes the previous `dist`, runs the
TypeScript compiler with `noEmitOnError`, and removes output again if the compiler
fails. The compiler has a requested 30-second subprocess timeout. Only this
component's `dist` is owned by that command; previously built browser bundles have
their separate build lifecycle. `npm run test:build --prefix examples/operator`
checks real compiler failure/recovery and controlled partial-write cleanup.
Use a single build per output directory and never serve it while building.
Host crashes, forced wrapper termination, filesystem failure and concurrent writers
are outside this cleanup guarantee; direct `tsc` invocation bypasses cleanup.
The scoped technology comparison is in [the build ADR](build-adr.json).

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

For an exclusively owned source, `mountObservationHost` adds page lifecycle
handling and one requested 20 ms refresh interval while the document is visible:

```js
import {mountObservationHost} from './dist/lifecycle.js';
const host = mountObservationHost(root, observation, 'en');
// Mount clears any earlier observation. After a new validated admission:
host.refresh();
// On logout or before removing/replacing this host:
host.dispose();
```

The source must implement fresh `view()` and `disconnect()` methods; the SDK
`Observation` satisfies that interface. Do not share its mutable instance with
another display host or return cached views. Mount, hiding/freezing/page departure,
reactivation and disposal clear the source. Hidden or suspended displays suppress
details even if the caller continues ingesting. Reactivation clears observations
admitted in the background and waits for a subsequent admission. Unsupported
visibility states remain inactive. Disposal removes the timer and five lifecycle
listeners as well as the panel. Late timer callbacks are inert.

If a visibility notification is missed, a later refresh still suspends when the
document reports hidden. A later visible state alone does not reactivate the
host; an activation event must first clear background observations. A late timer
callback while suspended cannot read the source or restart the timer. These are
event/clock checks, not a guarantee that a blocked browser will run cleanup.

Source-clearing or timer-creation failure latches unavailable guidance; after
repairing the host, dispose and remount it. Reader exceptions withdraw details
without copying their text and can recover on a later independent read. The
adapter delegates revocation to `source.disconnect()`: a plain SDK `Observation`
clears local state, while `createObservationSource` also aborts its owned ingress.
The adapter does not independently authorize or implement remote cleanup. The
caller must stop any separately owned session on logout. It does not erase copies
held elsewhere. Timer scheduling and page lifecycle delivery are browser/OS
assumptions, not measured deadlines or a reliable suspend detector.

The SDK archive is tested for Node. `npm run build:browser --prefix examples/operator`
now recompiles the SDK and these components, then produces a self-contained
`browser-dist/aethron-observation.mjs`. An authorized browser host can import
`Observation`, `observe`, `createObservationSource`, `presentObservation`, `mountObservationPanel` and
`mountObservationHost`, `mountConnectionControls` and `mountObservationClient` from that module. It contains the existing generated
validators; no CDN, package loader or runtime schema compiler is needed. The build
tool is development-only and pinned in the lockfile. A populated npm cache permits
offline dependency preparation with `npm ci --offline --ignore-scripts`.

Deploy the component together with `LICENSE`, `AJV-LICENSE`, `ESBUILD-LICENSE`,
`STATE-HELP.json`, `ACTION-HELP.json` and `manifest.json`. The manifest hashes the exact compiled runtime bytes supplied to the bundler and
output bytes; it
does not attest the full source/toolchain closure or authorize a release. The build
removes its previous named outputs before compiling, rejects changes to its
explicit runtime dependency list, and writes the manifest last. An absent manifest
means the build is incomplete. Do not serve the output directory during a build;
copy a completed, verified artifact into the host's versioned distribution.

Guidance sources are captured before compilation and checked again after compilation
and bundling. A changed guidance source fails the build and removes all named
artifacts; help generation uses the captured text. Use an exclusively owned,
stable build workspace: these comparisons cannot detect transient edits reverted
between checks, and they do not attest the compiler or full source tree.

Tests import the bundle from a data URL without external-module resolution and
with string code generation disabled, compare admission with the Node SDK, and
rebuild it for local byte reproduction. These remain Node/structural DOM checks,
not browser acceptance. ES2022 output does not polyfill runtime APIs. In particular,
strict wire ingress requires JSON.parse reviver context as well as Fetch streams,
TextDecoder and structuredClone. Actual browser versions, transport/CORS policy,
CSP, keyboard/accessibility behavior and installed-product acceptance are unverified.

The panel updates existing controls without replacing them on refresh. Content
uses text nodes; status has polite/atomic live-region attributes. Those semantics
still require real-browser keyboard/focus and assistive-technology acceptance.
Unsupported locales throw `unsupported_locale` before changing the view. Reader
exceptions become fixed invalid guidance without including exception text.
If a reader or input getter invokes another refresh or changes the locale, only
the newest refresh can update the panel. An interrupted older refresh cannot
restore withdrawn details or mix its earlier translation with the newer locale.
Callbacks and DOM objects remain trusted host code, not an isolation boundary.

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
[panel implementation plan](RENDERER-PLAN.md). The optional host has its own
[lifecycle ADR](lifecycle-adr.json) and [closed schema](lifecycle-adr.schema.json).
Browser packaging has a [technology decision](browser-adr.json) and
[closed schema](browser-adr.schema.json).

For SDK transport composition, create a source and mount the lifecycle host before
starting its session:

```js
import {createObservationSource, mountObservationHost} from './browser-dist/aethron-observation.mjs';
const source = createObservationSource();
const host = mountObservationHost(root, source, 'en');
// Authorization and these request parameters belong to the containing product.
const completion = source.start(base, token, profile, callerSignal);
// Attach the containing application's error handler immediately.
completion.catch(reportClientError);
// On logout/removal: clears display and revokes this source before aborting it.
host.dispose();
await completion.catch(() => {});
```

The source reads its current admitted observation at each refresh; it never renews
a lease from a saved callback snapshot. Hiding/freezing/page departure clears the
display and aborts that source. Visibility restoration does not reconnect. The
containing product may explicitly start a new authorized session after the previous
start promise settles and its own visibility/permission checks pass. Concurrent
starts reject with `observer_busy`. The source adds no timer, so the lifecycle host
remains the sole display scheduler. Current conditions remain UNKNOWN. This
composition has structural DOM and bundled Node tests; actual browser, accessible
operator workflow and installed-product acceptance remain pending.

### Explicit connection controls

`mountConnectionControls(root, operation, locale)` adds local Start/Stop buttons,
status and contextual help. It starts disabled and never reconnects automatically.
A host operation owns authorization and the SDK session:

```js
import {createObservationSource, mountObservationHost, mountConnectionControls}
  from './browser-dist/aethron-observation.mjs';
const source = createObservationSource();
const display = mountObservationHost(observationRoot, source, 'en');
const controls = mountConnectionControls(connectionRoot, {
  start: signal => source.start(origin, token, profile, signal),
  disconnect: () => { source.disconnect(); display.refresh(); },
}, 'en');
controls.setEnabled(hostCanRequest); // UI availability only; server authorization still required.
// On account/permission withdrawal:
controls.setEnabled(false);
// On removal:
controls.dispose();
display.dispose();
```

Supply exclusively owned roots and one exclusively owned session operation.
`start(signal)` must settle only after session cleanup, honor cancellation, and
perform the host's current permission checks. `disconnect()` must synchronously
clear the source and refresh any observation display. The component neither
receives credentials nor authenticates the host callback. It cannot force a
callback that ignores cancellation to settle; Start remains disabled meanwhile.
Start is also blocked while `disconnect()` is executing, including reentrant
callback attempts that re-enable the controls. These attempts are ignored rather
than queued. After withdrawal returns successfully, a later explicit Start can
request a session if the host has enabled the controls.

Stop, access withdrawal, hidden/unknown visibility, freeze, page departure and
reactivation withdraw the session. Returning does not reconnect. A disconnect
failure latches unavailable controls until remount. Request failures use fixed
local guidance and can be explicitly retried. A pending request is labelled
“Observation session requested”, never authenticated, connected or current.

The seven states (`unavailable`, `paused`, `idle`, `requested`, `stopping`,
`stopped`, `failed`) each have a `connection.<state>` contextual topic in English
and Swedish. Buttons expose `connection.start` / `connection.stop` feature IDs.
The containing application calls `setLocale` on both controls and display to keep
its language selection consistent. These local topics are not a searchable,
role-aware, release-SHA-bound P19 Help Center. Account workflows, actual browser
keyboard/screen-reader acceptance and customer distribution remain unfinished.
The [connection ADR](connection-adr.json) records the technology comparison and
four architecture views; the bundle uses an explicit runtime-module allowlist (see its manifest).

### One observation client view

`mountObservationClient` composes the observation display, explicit connection
controls and their bilingual contextual guidance into one owned root. It starts
unavailable and reads no source until enabled **and** explicitly started. Its
single language selector updates both panels; `setLocale` does the same.

```js
import {createObservationSource, mountObservationClient} from './browser-dist/aethron-observation.mjs';

const source = createObservationSource();
const client = mountObservationClient(document.querySelector('#observation-client'), {
  view: () => source.view(),
  disconnect: () => source.disconnect(),
  start: signal => source.start(origin, token, profile, signal),
}, 'en');
// The containing application obtains origin/token/profile and enforces access.
client.setEnabled(true); // Makes Start available; never starts automatically.
// On logout/access loss, call client.setEnabled(false) before changing credentials.
// On removal, call client.dispose(). A pending start remains gated through cleanup.
```

The adapter must exclusively own its source, honor the supplied signal, and settle
`start` only after reception and cleanup. Stop, access loss and page suspension
revoke the local view before invoking adapter cleanup. The display refresh runs
even when cleanup throws, and failed cleanup disables further starts. Enabling
again cannot revive old observations. This local gate does not replace host/service
authorization and does not prove remote session deletion.

The containing client guards the shared adapter while either child withdraws it.
A Start dispatched by a synchronous cleanup callback cannot reach the session
adapter, including during page reactivation before connection controls process
the same event. Recursive adapter clearing fails closed. After successful cleanup
and settlement, an independent explicit Start can proceed. These guarantees cover
component callback ordering, not independent operations performed by host code.

For custom compositions, the optional fourth argument to `mountObservationPanel`
and `mountObservationHost` is a locale-request callback. A button delegates to it;
the containing owner must call `setLocale` to commit the selection. Without that
argument the original local language selection remains unchanged.

The component has no account UI, persistent state or complete release-bound help
inventory. Full P19 search, onboarding, role coverage and independent installed
browser/accessibility acceptance remain open. [Client decision](client-adr.json)
and [scope](CLIENT-PLAN.md) describe this software boundary.

### Packaged state-guidance inventory

The browser build emits `browser-dist/STATE-HELP.json`, covered by the artifact
manifest. It derives the current locale/state sets and literal title/body text
from the actual presenter and connection source using the pinned TypeScript
compiler AST. Missing/extra state translations, duplicate keys, malformed source
or executable expressions fail the build. No source evaluation is used.

The inventory binds ten state topics in English and Swedish to source hashes and
the distributed module hash. The bundle tests execute every state, open its
native contextual details entry, and compare rendered titles/bodies in both
locales with the packaged inventory. This catches disconnected or stale help
bindings as well as unexercised new state topics. The build requires local Git
metadata: it records HEAD, observes dirty status before and after compilation,
rejects a changed HEAD, and emits `release_sha: null` for dirty builds. A clean
revision binding is unsigned component provenance, not product release approval.

This file deliberately says `product_help_complete: false`. It covers ten state
topics; the companion `ACTION-HELP.json` covers the four shipped buttons.
Both inventories list remaining product coverage: routes and role permissions,
search and onboarding, manuals and installed-product acceptance. Those gaps
continue to block full P19.7 acceptance. It does not contain administrator procedures,
credentials or sensor values. [State-help decision](state-help-adr.json) records
parser alternatives and the supported source grammar.


### Contextual button help

Each of the four buttons (English, Svenska, Start and Stop) has visible bilingual
text associated through `aria-describedby`, a stable `data-feature` action ID,
and a matching `data-help-action` paragraph. Descriptions stay readable when a
button is disabled. Changing language updates both panels and their help without
starting a session. Stop withdraws the local observation and requests cancellation;
its help does not claim confirmed remote deletion. IDs identify DOM nodes only.
The host exclusively owns the component DOM. Disposal clears descriptions and
removes their links; clients from one loaded module share a document counter.
Allocation checks existing IDs in the document and mount-root tree, including
shadow roots and detached subtrees. It tries at most 32 candidates before failing;
the containing client cleans up a partial mount. DOM lookup cost depends on host
tree size. The host must coordinate later ID changes, moving mounted roots between
trees, or combining detached trees created by separately loaded module copies.

`ACTION-HELP.json` supplements `STATE-HELP.json` in the browser distribution. It
extracts the literal action union and English/Swedish dictionary, binds source and
module bytes, and records the same clean/dirty Git provenance rules. Negative
checks reject missing or extra entries and executable expressions. The offline
bundle check compares **every button** to the inventory in both locales, resolves
every contextual description link, and executes all four actions. A new button
without help, an unused help action, text/locale mismatch or broken link fails.
The manifest hashes both files; failed builds remove both inventories.

This covers four implemented button actions, not a complete Help Center. Native
state-help disclosures retain their existing guidance. Role/permission inventories,
search, onboarding, manuals, actual browser/screen-reader behavior and independent
installed-product acceptance remain unfinished. `product_help_complete` stays
false. See [action-help decision](action-help-adr.json) and its four C4 views.
