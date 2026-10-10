# P2.3 provider execution failure boundary

Scope: one correction to the pinned RGB detector's Core ML execution path.
Capture clocks, sensor registration, model bytes and frozen thresholds are unchanged.

## Technology decision (2026-10-09)

Requirement: a selected provider's execution failure must propagate to the
worker's fixed `model_error`/UNKNOWN path, without retrying the same frame under a
different provider label. The existing explicit Core ML/CPU node partition is
still allowed; it does not establish all-accelerator execution.

Primary-source research: ONNX Runtime's [Python API](https://onnxruntime.ai/docs/api/python/api_summary.html)
provides `disable_fallback()`. Its [Python implementation](https://onnxruntime.ai/docs/api/python/modules/onnxruntime/capi/onnxruntime_inference_collection.html)
catches native `EPFail` in `run()`, rebuilds with fallback providers, then retries.
The [Core ML provider documentation](https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html)
separately describes node support and compute-unit options.

Choose the Python session API because it owns the retry mechanism. Checking
providers only after inference would allow the unrequested retry to execute.
A C++/Rust wrapper would add an ABI and packaging boundary without changing the
Python retry policy; replacing the runtime would require fresh model equivalence
and device qualification. No new production dependency is introduced.

## Retained counterexample and verification

With pinned ONNX Runtime 1.30.0, a real Python `Session.run()` wrapping an injected
native `EPFail` printed that it was falling back to CPU and returned an empty
successful inference. `test_execution_failure_cannot_retry_on_cpu` failed with
`AssertionError: EPFail not raised` before the fix. Session construction remains
substituted in this test; it does not claim real model or accelerator execution.
The small synthetic model fixture still passes the real length/digest check under
test-only pins. The separate tamper test covers production model admission.

The correction disables the runtime retry before accepting the created session.
The startup provider-presence check remains required because constructor fallback
can already have removed Core ML. Tests also cover absent Core ML and successful
inference with the declared provider still present. The existing worker catches
propagated exceptions and emits its fixed error, without raw exception text.

The provider-boundary workflow installs pinned binary packages and runs these
tests on Linux, retaining logs even on failure. It exercises
the ORT Python boundary with injected native results, not accelerator performance.
Existing software CI owns the full fuzz, temporal, packaging and reproduction
jobs. No local broad fuzz, full matrix, Docker or accelerator build is required
for this increment. Hosted execution remains pending until an actual run exists.

Linux continuation: Python 3.13.5 with ONNX Runtime 1.30.0, OpenCV 4.13.0 and
NumPy 2.3.5 passed all six focused vision tests without skips. Targeted Ruff,
formatting, Bandit and workflow YAML checks passed. An earlier invocation before
dependency installation completed skipped four provider tests; that output is
retained separately and is not counted as verification. ORT emitted a sandbox
telemetry-identifier persistence warning; it did not prevent the regressions.
