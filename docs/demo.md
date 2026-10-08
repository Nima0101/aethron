> Historical v0.1 evidence/procedure. See the [current v3 record](demo-v3.md).

# Reproduce the demonstration
Run `python3 scripts/capture_demo.py` to execute the actual CLI and capture 22 synthetic scenarios as JSON and asciicast events with measured process-relative timestamps. Inputs are original fixtures, never camera/radar recordings. `docs/assets/replay.html` is generated from those results. Its controls navigate fixture snapshots; geometry expires after 200ms without new evidence. The table remains visibly historical after expiry. Human envelopes never imply identity or cross-frame matching.

Run `.venv/bin/python scripts/terminal_gif.py` for the slowed textual GIF replay from actual results. This is explicitly a rendered result replay, not a screenshot or live-hardware video. No physical scene is fabricated.

A real Chromium browser launch was attempted using installed Playwright tooling. The development sandbox denied Chromium's Mach-port bootstrap registration (`Permission denied (1100)`), so browser screenshot/video and real-browser timer verification are blocked locally. Do not relabel this as browser-verified. `scripts/browser_check.py` prepares the exact test/recording for an environment that permits Chromium; optionally set `RESCUESENSE_BROWSER` to an installed executable. CI runs that check with a provisioned browser. No sandbox bypass was attempted.

Flutter's current public repository was re-opened on 2026-10-08 before final presentation. Applied principles: immediate product purpose, fast executable path, visible evidence/limits, architecture and contribution links. No Flutter text, logo or artwork was copied. Original vector assets depict actual implementation boundaries.
