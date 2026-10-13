# Containing observation client

Scope: compose the existing read-only display lifecycle and connection controls
into one exclusively owned root. Default unavailable; no source read until an
explicit enabled session. Stop/access withdrawal removes local observations even
when an adapter fails to clear. One language choice updates both panels and help.
The host supplies the authorized session adapter; no account, credential storage,
server policy or actuation is introduced.

Technology decision: native DOM with TypeScript function contracts. Current
comparison includes checked ECMAScript, ReScript bindings, Elm ports and Lit
lifecycle. Synchronous source withdrawal and a single locale owner are the decisive
constraints; no additional rendering runtime is required. See client-adr.json.

Sequence: eight failing missing-component tests; typed composition and locale
request seam; focused lifecycle/permission/reentry tests; standalone bundle test;
closed ADR and source-bound evidence; exact staged local commit. Preserve all
negative results and existing browser/customer qualification limits. No agents.
This small composition does not complete P12 or the P19 help coverage inventory.
