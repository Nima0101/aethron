# P12 connection control slice

Implement inside this lane with the owner's autonomous execution and no-subagent
rules. No separate approval pause. [Decision](connection-adr.json) compares native
HTML/TypeScript, checked ECMAScript, Lit, Elm and ReScript against an offline,
single-operation, synchronous-withdrawal host boundary.

1. Demonstrate missing-component failures for default denial, explicit start/stop,
   overlapping requests, cleanup, lifecycle, locale, host failures and disposal.
2. Implement native buttons, a polite status region and local contextual help.
   Default disabled; do not accept credentials or initiate transport directly.
3. Exercise all seven states in both locales and compose with the actual SDK
   source/display. Add a closed ADR check and browser-artifact consumer test.
4. Compile and run focused operator/bundle checks, preserve negative results and
   hash current sources/artifacts. Stage a cohesive slice for the commit bridge.

Host contract: `start(signal)` encompasses the session and cleanup, and honors
cancellation. `disconnect()` synchronously clears its source and refreshes its
observation display. Host/server enforce authorization; `setEnabled` is only UI
availability. No native browser or complete P19 acceptance claim is made.
