"""Real browser expiry/UI check and recording. Optional external browser prerequisite."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def launch_browser(playwright):
    """Use the matching Playwright browser, or a verified local cache fallback.

    Fallback applies only when the expected executable is missing, not when
    Chromium starts but fails (sandbox, permissions, version incompatibility).
    """
    selected = os.environ.get("AETHRON_BROWSER")
    if selected:
        return playwright.chromium.launch(executable_path=selected), selected
    try:
        return playwright.chromium.launch(), "playwright-default"
    except Exception as error:
        if "Executable doesn't exist" not in str(error):
            raise
        cache = Path.home() / "Library/Caches/ms-playwright"
        candidates = sorted(
            cache.glob(
                "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell"
            ),
            reverse=True,
        )
        if not candidates:
            raise
        failures = []
        for candidate in candidates:
            try:
                return playwright.chromium.launch(executable_path=str(candidate)), str(candidate)
            except Exception as fallback_error:
                failures.append(str(fallback_error))
        raise RuntimeError(
            "Installed Chromium fallback(s) failed: " + "; ".join(failures)
        ) from error


def run():
    out = ROOT / "build/browser"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser, engine = launch_browser(p)
        context = browser.new_context(
            viewport={"width": 1200, "height": 1000}, record_video_dir=str(out)
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.clock.install(time=datetime(2026, 1, 1, tzinfo=timezone.utc))
        page.clock.pause_at(datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc))
        page.goto((ROOT / "docs/assets/replay.html").as_uri())
        page.evaluate("show(18)")
        assert page.locator('[data-detection="human"]').count() == 1
        assert "thermal_person" in page.locator("#claims").inner_text()
        await_text = page.locator("#claims").inner_text()
        assert "rgb" not in await_text
        page.screenshot(path=str(out / "person-blackout.png"), full_page=True)
        page.clock.run_for(201)
        assert page.locator("[data-detection]").count() == 0
        assert "UNKNOWN" in page.locator("#validity").inner_text()
        page.evaluate("show(19)")
        assert page.locator("[data-detection]").count() == 0
        assert "STOP" in page.locator("#action").inner_text()
        page.evaluate("show(21)")
        assert page.locator("[data-detection]").count() == 0
        assert "PRESENT" in page.locator("#claims").inner_text()
        page.screenshot(path=str(out / "coarse-radar.png"), full_page=True)
        assert not errors, errors
        context.close()
        browser.close()
    (out / "result.json").write_text(
        json.dumps(
            {
                "expiry": "passed",
                "blackout": "passed",
                "through_obstruction": "passed",
                "evidence": "browser synthetic replay only",
                "browser_engine": "playwright-default"
                if engine == "playwright-default"
                else Path(engine).parent.parent.name,
            }
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
