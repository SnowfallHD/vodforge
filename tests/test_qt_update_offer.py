"""An update found when VODForge opens is shown at once, once per version.

The "Update available" notice was lost when the header was rebuilt (Oct 18), so
from then on an update showed only if the user opened Settings and pressed
"Check for updates". Automatic updates still install on quit; the window tells
the user and offers Install now.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest

from tests.test_qt_update_check_guidance import update_click, update_notice_scene
from yt_downloader.qt_quick import update_session
from yt_downloader.updates import ReleaseInfo

__all__ = ["update_notice_scene"]


def release(version: str) -> ReleaseInfo:
    return ReleaseInfo(
        version=version,
        tag_name=f"v{version}",
        name="VODForge",
        html_url="https://github.com/SnowfallHD/vodforge/releases/latest",
        notes="",
        assets=(),
    )


@pytest.fixture
def found(update_notice_scene, monkeypatch):
    app, bridge, window = update_notice_scene
    # Every platform has an installer; no download starts in these tests.
    monkeypatch.setattr(
        update_session, "release_asset_for_platform", lambda _release: object()
    )
    monkeypatch.setattr(bridge._updates, "download", lambda **_kw: False)
    bridge._updates.current_version = "0.2.6"

    def check_finds(version: str) -> None:
        bridge._updates._begin_observation("automatic")
        bridge._updates.stage = "check"
        bridge._updates.events.put(("checked", release(version)))
        bridge._pump()
        QTest.qWait(50)

    return app, bridge, window, check_finds


def popup(window):
    return window.findChild(QObject, "updatePopup")


def test_update_found_at_launch_opens_the_update_window_once(found):
    _app, _bridge, window, check_finds = found
    check_finds("0.2.7")
    assert popup(window).property("visible")
    heading = window.findChild(QObject, "updateHeading").property("text")
    assert heading == "Update available"
    update_click(window, window.findChild(QObject, "updateDismiss"))  # Later
    assert not popup(window).property("visible")
    check_finds("0.2.7")  # the 6-hour repeat finds the same release
    assert not popup(window).property("visible")
    check_finds("0.2.8")  # a newer one is shown again
    assert popup(window).property("visible")


def test_update_window_waits_for_an_open_dialog(found):
    _app, _bridge, window, check_finds = found
    settings = window.findChild(QObject, "downloadSettingsPopup")
    update_click(window, window.findChild(QObject, "headerSettingsButton"))
    assert settings.property("visible")
    check_finds("0.2.7")
    assert not popup(window).property("visible")
    settings.setProperty("visible", False)
    QTest.qWait(900)
    assert popup(window).property("visible")


def test_no_window_when_vodforge_is_up_to_date(found):
    _app, _bridge, window, check_finds = found
    check_finds("0.2.6")
    QTest.qWait(500)
    assert not popup(window).property("visible")
