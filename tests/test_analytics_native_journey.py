"""Real Tk event-loop journeys with isolated permission/transport boundaries.

This is source-owner integration evidence, not an installed-app or OS-focus test.
"""

import os
import time
import tkinter as tk

import pytest

from yt_downloader import analytics_startup as module
from yt_downloader.analytics_consent import AnalyticsConsentOwner

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="requires native Tcl/Tk"
)


@pytest.mark.parametrize(
    "scenario", ["default-on", "opt-in", "unknown", "slow", "retry"]
)
def test_real_event_loop_permission_journey(tmp_path, monkeypatch, scenario):
    root = tk.Tk()
    root.withdraw()
    owner = AnalyticsConsentOwner(tmp_path)
    opened, prompts, issued = [], [], []
    begun = time.monotonic()
    calls = []

    def resolve(*, deadline):
        calls.append(True)
        time.sleep(3.0 if scenario == "slow" else 0.05)
        mode = scenario
        if scenario == "retry":
            mode = "unknown" if len(calls) == 1 else "default-on"
        if mode not in {"default-on", "opt-in"} or time.monotonic() >= deadline:
            mode = "unknown"
        owner.update(mode=mode)
        return mode

    monkeypatch.setattr(owner, "resolve", resolve)
    monkeypatch.setattr(module, "production_telemetry_allowed", lambda: True)
    monkeypatch.setattr(
        module.webbrowser,
        "open",
        lambda *a, **k: opened.append(time.monotonic() - begun),
    )
    monkeypatch.setattr(module, "issue_claim", lambda *a: issued.append(a) or True)
    monkeypatch.setattr(module, "cancel_claim", lambda *a: None)
    startup = module.AnalyticsStartup(root, owner, tk.BooleanVar(root), lambda _: None)
    monkeypatch.setattr(
        startup, "_prompt", lambda: prompts.append(time.monotonic() - begun)
    )
    try:
        startup.start()
        until = time.monotonic() + (3.2 if scenario == "slow" else 0.5)
        while time.monotonic() < until:
            root.update()
            time.sleep(0.005)
        assert len(opened) == 1
        assert opened[0] < 2.9
        needs_choice = scenario in {"opt-in", "unknown", "slow"}
        assert len(prompts) == int(needs_choice)
        if needs_choice:
            assert prompts[0] < 2.9
            assert not issued
            startup.variable.set(True)
            until = time.monotonic() + 0.2
            while time.monotonic() < until:
                root.update()
                time.sleep(0.005)
        assert len(issued) == 1
        assert len(opened) == 1
        print(
            {
                "scenario": scenario,
                "browser_seconds": opened,
                "prompt_seconds": prompts,
                "region_attempts": len(calls),
            }
        )
    finally:
        startup.close()
        root.destroy()
