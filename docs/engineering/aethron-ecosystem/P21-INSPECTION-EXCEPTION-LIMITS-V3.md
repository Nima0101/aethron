# C08 CLI exception disclosure limits — V3, partial

Decision: **CLARIFY handled-error scope and retained context.** The prior
invocation-name correction and its output controls remain valid. Fixed stderr
text is narrower than exception-object sanitization or a promise to handle every
fault. The main function docstring now states this distinction; runtime behavior
is unchanged. Full V3 technology review remains incomplete at C01.

For the injected OSError at calibration-file opening, main prints the existing
fixed diagnostic, leaves stdout empty and raises SystemExit(2). The original
OSError remains reachable through the exit object's `__context__`, including its
synthetic private message. An embedding caller must not treat that object or its
traceback state as sanitized output. The CLI does not redact arbitrary caller
logging. Python's [exception-context documentation](https://docs.python.org/3.13/library/exceptions.html#exception-context)
explains retained context; [argparse](https://docs.python.org/3.13/library/argparse.html#argparse.ArgumentParser.exit)
describes exit status and optional diagnostic emission.

A new method injects RuntimeError, MemoryError, KeyboardInterrupt and SystemExit
at the same file-open seam. Each original object propagates; no fixed diagnostic
or report is written to the captured streams. These tests catch the exception
in-process. They do not claim that a launched interpreter or logging framework
will hide its traceback, that stderr failures are contained, or that a real OOM
or operating-system signal was exercised. No file is opened and no image
processing runs in these fault controls.

One existing method gained context assertions and one method was added. All four
CLI diagnostic methods pass before and after the docstring change. No production
RED or security remediation is claimed. Ruff/format pass after formatting the
new test's argument list. Bandit retains four existing LOW subprocess findings
(B404 once and B603 three times), identical to the parent by rule/severity/message.
The module AST is unchanged after removing docstrings. No input contract,
exception catch list, processing, return status or output format was changed.

Historical failures, qualification limits and the prior partial-write disclaimer
remain. No runtime selection, benchmark, certification or completion claim is
made. See [source-bound checks](evidence/phase2/inspection-exception-limits-v3.json).
