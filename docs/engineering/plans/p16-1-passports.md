# P16.1 implementation plan

Goal: implement the [passport v1 contract](../../architecture/interop/passport-v1.md)
without connecting declarations to motion authority. Native execution, no sub-agents.

1. Add failing canonicalization and negative schema tests in `tests/test_passports.py`.
   Implement `aethron/passports.py`: strict byte-bound parser, canonical payload API,
   DSSE framing and a closed capability/evidence vocabulary. Run focused unittest.
2. Add actual-signature, trust scope, expiry, revocation, rollback, missing-backend and
   malformed-envelope tests. Implement offline `verify` with immutable fixed results;
   pin optional Ed25519 dependency and exercise the exact signed canonical bytes.
3. Add portable golden and negative fixtures, a short bounded deterministic mutation
   test, and a focused hosted job for the optional crypto dependency. Run targeted
   unittest, Ruff and Bandit. Check frozen files unchanged and public diff for leaks.
4. Stage only this increment and create a cohesive local commit. If sandbox Git metadata
   is read-only, submit the authorized commit bridge request in the private lane runtime;
   verify its committed SHA and noreply identity on continuation before public delivery.
   Reconcile protected main at a safe checkpoint and publish a small sanitized PR.
   Do not run heavy local matrix/clone/fuzz/VM jobs or wait/poll hosted CI.

Review focus: noncanonical signed bytes; boolean-number confusion; stale/replayed trust;
issuer/subject/capability confusion; negative evidence preserved; no authority escalation.
