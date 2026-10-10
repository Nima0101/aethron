# P12 action help

Scope: four already implemented read-only client buttons. Keep source authentication
and authorization in the host/service; retain existing start/stop and withdrawal
behavior. Help is public fixed text, offline, English and Swedish, with no source
or credential data. Routes, roles, search, onboarding and full product acceptance
remain separate unfinished work.

Technology decision: retain TypeScript/native DOM for four synchronous visible
paragraphs associated via aria-describedby. Compare Lit custom elements (reactive
update lifecycle), ReScript DOM bindings (alternative static type boundary), and
Rust/wasm-bindgen (native memory domain with JS DOM bindings). No cross-platform
computation or custom-element reuse requirement makes those additional boundaries
materially better for these text-only, synchronous DOM mutations. This is a
constraint comparison, not a speed benchmark. Build-time AST extraction is retained
from the state-help tool with a separate versioned action inventory.

1. Run negative tests for missing descriptions, locale coordination, unique links,
   disposal and source-derived inventory (seven initial failing tests retained).
2. Attach visible native descriptions to each button; keep short button names.
3. Extract and package literal bilingual action help, source and artifact hashes;
   reject missing or extra translations and unsupported syntax.
4. Exercise every actual bundled button against the inventory, offline. Verify
   descriptions, language changes, explicit start/stop and cleanup. Run focused
   operator and SDK contract checks, then stage a cohesive local commit.

No subagents or heavy qualification. Structural DOM checks are not native browser,
screen-reader or independently installed customer acceptance.
