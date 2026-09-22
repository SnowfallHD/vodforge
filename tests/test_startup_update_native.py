"""Real Tk startup dispatch while the update provider is blocked or offline."""

import os
import sys
import time
from threading import Event
from types import SimpleNamespace

import pytest

from scripts.focus_ui_preview import isolated_preview_services
from yt_downloader import app as app_module
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.whats_new import WhatsNewOwner

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="Native display required"
)


def test_initial_update_dispatch_does_not_wait_or_block_first_ui(monkeypatch):
    monkeypatch.setattr(AnalyticsStartup, "start", lambda self: None)
    monkeypatch.setattr(EngagementUI, "start", lambda self: None)
    monkeypatch.setattr(WhatsNewOwner, "start", lambda self: None)
    proxy = SimpleNamespace(**vars(sys))
    proxy.frozen = True
    monkeypatch.setattr(app_module, "sys", proxy)
    entered, release = Event(), Event()
    calls = []

    def fetch():
        calls.append(time.monotonic())
        entered.set()
        release.wait(5)
        raise OSError("offline fixture")

    monkeypatch.setattr(app_module, "fetch_latest_release", fetch)
    with isolated_preview_services():
        app = app_module.DownloaderApp()
        callbacks = []
        ready = time.monotonic()
        app.after(50, lambda: callbacks.append(time.monotonic()))
        app.deiconify()
        try:
            deadline = time.monotonic() + 1
            while (
                not callbacks or not entered.is_set()
            ) and time.monotonic() < deadline:
                app.update()
                time.sleep(0.002)
            assert entered.is_set() and len(calls) == 1
            assert calls[0] - ready < 0.25, (
                "Startup update dispatch retained a fixed delay"
            )
            assert callbacks and callbacks[0] - ready < 0.25
            assert app.winfo_ismapped() and app.update_worker.is_alive()
            app._check_for_updates(silent=True)
            assert len(calls) == 1
        finally:
            release.set()
            if app.update_worker:
                app.update_worker.join(2)
            app._request_application_close()
            deadline = time.monotonic() + 3
            while app.tk.call("info", "commands", ".") and time.monotonic() < deadline:
                app.update()
                time.sleep(0.005)
            if app.tk.call("info", "commands", "."):
                app.destroy()
