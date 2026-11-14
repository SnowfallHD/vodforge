"""A server notice opens once in the real window and records its outcome."""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QEventLoop, QObject, QTimer

from tests.test_qt_scene_port import qt_app
from yt_downloader.app_notices import parse_notices
from yt_downloader.qt_quick import main as qt_main


def settle(milliseconds=30):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


NOTICE = {
    "id": "discord-open",
    "title": "Join the VODForge Discord",
    "body": "Ask questions and hear about updates first.",
    "link": {"label": "Join Discord", "url": "https://discord.gg/example"},
}


@pytest.fixture
def window_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    monkeypatch.setattr(qt_main, "SHOWCASE_MODE", "none")
    monkeypatch.setattr(qt_main, "__version__", "0.2.8")
    qt_app()
    bridge = qt_main.Bridge(None)
    bridge._timer.stop()
    bridge._engagement.presented_welcome()
    bridge._settings["social_invitation_dismissed"] = True
    events = []
    monkeypatch.setattr(
        bridge,
        "_record_update_feature",
        lambda feature, action, dimensions=None: events.append((feature, action)),
    )
    opened = []
    monkeypatch.setattr(
        qt_main.QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        yield bridge, window, events, opened
    finally:
        bridge.close()


def offer(bridge):
    bridge._notices = parse_notices({"version": 1, "notices": [NOTICE]})
    bridge._social_idle_since = time.monotonic() - 10
    bridge.checkEditorial(True)
    settle()


def test_a_notice_opens_once_and_its_link_opens(window_bridge):
    bridge, window, events, opened = window_bridge
    popup = window.findChild(QObject, "noticePopup")
    offer(bridge)
    assert popup.property("visible")
    assert bridge.noticeTitle == "Join the VODForge Discord"
    assert bridge.noticeLinkLabel == "Join Discord"
    assert bridge._settings["notices_seen"] == ["discord-open"]
    popup.setProperty("linkChosen", True)
    popup.close()
    settle()
    assert opened == ["https://discord.gg/example"]
    assert events == [("notice", "shown"), ("notice", "opened")]
    # Shown once: the same notice never opens again.
    offer(bridge)
    assert not popup.property("visible")
    assert events == [("notice", "shown"), ("notice", "opened")]


def test_closing_records_closed_and_opens_nothing(window_bridge):
    bridge, window, events, opened = window_bridge
    popup = window.findChild(QObject, "noticePopup")
    offer(bridge)
    popup.close()
    settle()
    assert opened == []
    assert events == [("notice", "shown"), ("notice", "closed")]


def test_a_notice_waits_while_something_else_is_happening(window_bridge, monkeypatch):
    bridge, window, events, _opened = window_bridge
    popup = window.findChild(QObject, "noticePopup")
    bridge._notices = parse_notices({"version": 1, "notices": [NOTICE]})
    bridge.checkEditorial(False)  # the window reports another dialog or typing
    bridge._social_idle_since = time.monotonic()
    bridge.checkEditorial(True)  # not idle long enough yet
    with monkeypatch.context() as patch:
        patch.setattr(type(bridge._runtime), "busy", property(lambda _self: True))
        bridge._social_idle_since = time.monotonic() - 10
        bridge.checkEditorial(True)  # a download is running
    settle()
    assert not popup.property("visible")
    assert events == []
    assert "notices_seen" not in bridge._settings
