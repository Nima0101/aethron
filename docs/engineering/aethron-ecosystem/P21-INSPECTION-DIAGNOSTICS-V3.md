# C08 inspection diagnostics — V3, partial

Decision: **FIX invocation-name disclosure and CLARIFY help wording.**
The offline intensity command used argparse's default program name, so help
could disclose a caller-selected executable basename. It now displays the public
module name. The module description now promises report buffering until input
validation, rather than incorrectly describing all stdout as following complete
success. Help intentionally writes stdout without inspecting a recording.

Three focused methods exercise help, four invalid argument cases, and a stubbed
file-open error. The help regression initially failed with the private fixture
basename in stdout; the two error methods passed. After correction all three
pass. Missing arguments, unknown options, invalid integer values and an OSError
with private text produce exit 2, empty stdout and the existing fixed diagnostic.
Help exits 0 and still describes the recording and pixel options.

These checks use synthetic argument strings and an injected file error. No
recording is opened, no calibration or raster computation runs, and no hardware
or timing claim is made. Report data still contains metadata; output buffering
is not transactional writing, redaction or an access-control boundary. A failing
output stream may receive a prefix, and this pass does not test interpreter
shutdown flushing, closed stderr, resource exhaustion or arbitrary exceptions.

The production AST differs only in the module docstring and parser prog value.
No sensor algorithm, input contract, threshold, dependency or record output
changes. Ruff and formatting pass. Bandit retains four LOW findings in preexisting
test subprocess code (B404 once, B603 three times), identical by rule, severity
and message to the baseline; production has no findings in that scan. This does
not claim a clean repository security scan or complete publication qualification.

The official [argparse documentation](https://docs.python.org/3.13/library/argparse.html)
(inspected 2026-10-10) documents the program-name default and explicit prog control.
This bounded diagnostic correction introduces no new component or runtime choice.
The full open-universe technology reassessment remains incomplete at C01; this
is not a KEEP/MIGRATE decision, benchmark or completion marker. Historical
negative evidence remains unchanged.

See [source-bound checks](evidence/phase2/inspection-diagnostics-v3.json).
