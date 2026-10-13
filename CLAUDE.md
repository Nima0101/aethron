# AETHRON Claude Code instructions

Read and follow the local `AGENTS.md`, active lane/task rules, and the controller's safety and concurrency requirements first. Preserve all existing instructions and access restrictions.

## Non-blocking CI, builds and tests

- Do not block the active Claude session on long waits, `sleep`, polling loops, `gh run watch`, `gh pr checks --watch`, or terminal commands that mostly wait for CI, builds, or tests. Use bounded foreground calls only when an immediate result is needed.
- Launch necessary long-running verification asynchronously within the project's approved runner/permission limits. A separate terminal process or lightweight watcher may monitor CI and record status, logs, artifacts, and exit codes **without any Claude/model calls**. Do not spawn extra coding agents just to monitor CI or create duplicate CI runs.
- While verification is pending, Claude must continue remaining independent implementation, code review, and short local checks. Do not treat `pending` or `queued` CI as unfinished code; track implementation progress separately from verification. Do not modify tested code without marking prior verification stale and rerunning applicable checks.
- Inspect verification results at meaningful milestones or when the watcher reports completion/actionable failure; never burn model turns on frequent idle polling. When a failure requires action, Claude must read the actual logs, analyze the root cause, fix the relevant code, and rerun targeted verification.
- If implementation is done and only external verification remains, save a clear checkpoint with the pending run IDs, what has been verified, and follow-up conditions, then yield instead of waiting. Never claim tests or release gates passed before actual evidence exists.
