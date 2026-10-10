# C09 worker exception disclosure — V3, partial

Decision: **CLARIFY message privacy versus propagated exception privacy.**
The earlier comment that no exception details leave the worker was too broad.
The fixed fault-message dictionary omits input and exception text. A failing
send callback, however, can propagate its own private error text with the
original failure as implicit exception context. A caller formatting that
traceback can disclose both. Message sanitization is not exception sanitization.
Callers must keep propagated tracebacks out of public output and apply their
own diagnostic access and retention controls.

A new synthetic control injects a manifest failure and a failing message sink.
It verifies the same sink exception propagates, retains the original exception
as context, and includes both fixture messages in a formatted traceback. The
attempted fault-message dictionary still omits them. Another control injects
KeyboardInterrupt before any recording opens: the interrupt propagates and
no message is sent. Neither case provides a final diagnostic-delivery guarantee.

Both new controls pass before and after the documentation correction. All four
worker claim methods pass; no RED production defect or privacy remediation is
claimed. Ruff/format pass; Bandit reports zero findings in the two checked files.
The executable production AST is unchanged. No provider, sensor computation,
recording, process supervisor, timing benchmark or physical device executes in
the new controls. Arbitrary callback behavior, provider cleanup failures and
supervisor traceback handling are not qualified by these checks.

Python's official [exception context documentation](https://docs.python.org/3.13/library/exceptions.html#exception-context)
(inspected 2026-10-10) describes implicit chaining and its traceback display.
This correction changes documentation and test evidence, not the execution
boundary or a language/runtime choice. Full V3 technology reassessment remains
incomplete at C01. No KEEP/MIGRATE decision or completion marker is introduced;
prior negative evidence remains unchanged.

See [source-bound checks](evidence/phase2/worker-exception-claims-v3.json).
