"""Release orientation eligibility and reopening through the existing Help menu."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEventLoop, QMetaObject, QObject, QPoint, Qt, QTimer
from PySide6.QtTest import QSignalSpy, QTest

from tests.test_qt_scene_port import qt_app
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.settings_store import load_settings


def settle(milliseconds=20):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    owner = qt_main.Bridge(None)
    owner._engagement.presented_welcome()
    owner._settings["social_invitation_dismissed"] = True
    owner._settings["whats_new_seen"] = "output-settings-presets-v2"
    try:
        yield owner
    finally:
        owner.close()


def test_new_editorial_id_is_eligible_once_and_waits_for_idle_ready_ui(
    bridge, monkeypatch
):
    requested = QSignalSpy(bridge.editorialRequested)
    bridge.checkEditorial(False)
    assert not bridge.editorialSlides
    with monkeypatch.context() as patch:
        patch.setattr(type(bridge._runtime), "busy", property(lambda _self: True))
        bridge.checkEditorial(True)
        assert not bridge.editorialSlides
    bridge.checkEditorial(True)
    assert bridge.editorialHeading == "What’s new"
    assert bridge.editorialFinishLabel == "Done"
    assert [s["key"] for s in bridge.editorialSlides] == [
        s.key for s in qt_main.HIGHLIGHTS
    ]
    bridge.checkEditorial(True)
    assert requested.count() == 1
    bridge.dismissEditorial(False)
    bridge._save_preferences()
    assert load_settings(bridge._settings_path)["whats_new_seen"] == qt_main.SHOWCASE_ID
    bridge.checkEditorial(True)
    assert not bridge.editorialSlides
    assert requested.count() == 1


@pytest.mark.parametrize(
    "mode,highlights", [("none", None), ("did-you-know", None), ("whats-new", ())]
)
def test_disabled_or_empty_release_cannot_open_whats_new(
    bridge, monkeypatch, mode, highlights
):
    monkeypatch.setattr(qt_main, "SHOWCASE_MODE", mode)
    if highlights is not None:
        monkeypatch.setattr(qt_main, "HIGHLIGHTS", highlights)
    assert not bridge.whatsNewAvailable
    assert not bridge.openWhatsNew()
    if mode != "did-you-know":
        bridge.checkEditorial(True)
        assert not bridge.editorialSlides


def test_manual_reopen_keeps_seen_receipt_and_never_duplicates_a_modal(bridge):
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    requested = QSignalSpy(bridge.editorialRequested)
    bridge.checkEditorial(True)
    assert not bridge.editorialSlides
    assert bridge.openWhatsNew()
    assert not bridge.openWhatsNew()
    assert not bridge.openWelcomeTour()
    assert requested.count() == 1
    assert bridge._settings["whats_new_seen"] == qt_main.SHOWCASE_ID
    bridge.dismissEditorial(False)
    assert bridge.openWhatsNew()
    assert requested.count() == 2


def test_manual_orientation_waits_for_consent_and_support_modal(bridge):
    analytics = bridge._analytics
    try:
        bridge._analytics = SimpleNamespace(settled=False)
        assert not bridge.openWhatsNew()
    finally:
        bridge._analytics = analytics
    bridge._support.kind = "feedback"
    assert not bridge.openWhatsNew()
    bridge._support.kind = ""
    assert bridge.openWhatsNew()


def test_shutdown_without_acknowledgement_leaves_orientation_eligible(bridge):
    bridge.checkEditorial(True)
    assert bridge.editorialSlides
    bridge._save_preferences()
    assert (
        load_settings(bridge._settings_path)["whats_new_seen"]
        == "output-settings-presets-v2"
    )


def test_seen_orientation_survives_actual_settings_reload(bridge):
    bridge.checkEditorial(True)
    bridge.dismissEditorial(False)
    bridge._save_preferences()
    restarted = qt_main.Bridge(None)
    try:
        restarted.checkEditorial(True)
        assert not restarted.editorialSlides
        assert restarted._settings["whats_new_seen"] == qt_main.SHOWCASE_ID
        assert restarted.openWhatsNew()
    finally:
        restarted.close()


def test_help_menu_pointer_opens_shared_popup_and_each_slide_fits(bridge, tmp_path):
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        menu = window.findChild(QObject, "helpMenu")
        assert QMetaObject.invokeMethod(menu, "open")
        settle(60)
        button = window.findChild(QObject, "helpWhatsNew")
        assert button is not None and button.isVisible()
        point = button.mapToItem(None, button.width() / 2, button.height() / 2)
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(point.x()), round(point.y())),
        )
        settle(30)
        popup = window.findChild(QObject, "editorialPopup")
        assert popup.property("visible")
        assert bridge.editorialHeading == "What’s new"
        assert not menu.property("visible")
        for index, slide in enumerate(bridge.editorialSlides):
            popup.setProperty("index", index)
            settle(30)
            title = window.findChild(QObject, "editorialSlideTitle")
            description = window.findChild(QObject, "editorialSlideDescription")
            assert title.property("text") == slide["title"]
            assert description.property("text") == slide["description"]
            for item in (title, description):
                assert item.isVisible()
                position = item.mapToItem(popup.property("contentItem"), 0, 0)
                assert position.y() >= 0
                assert (
                    position.y() + item.height()
                    <= popup.property("contentItem").height()
                )
            assert window.grabWindow().save(str(tmp_path / f"orientation-{index}.png"))
        popup.close()
        settle()
    finally:
        window.close()
        engine.deleteLater()
        settle()


@pytest.mark.parametrize("blocker", ["ui", "busy", "playback", "support", "editorial"])
def test_social_invitation_waits_for_idle(bridge, monkeypatch, blocker):
    bridge._settings["social_invitation_dismissed"] = False
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    bridge._social_idle_since = qt_main.time.monotonic() - 9
    requested = QSignalSpy(bridge.socialInvitationRequested)
    if blocker == "busy":
        monkeypatch.setattr(type(bridge._runtime), "busy", property(lambda _self: True))
    elif blocker == "playback":
        bridge._playback_binding = object()
    elif blocker == "support":
        bridge._support.kind = "feedback"
    elif blocker == "editorial":
        bridge._editorial_kind = "welcome"
    bridge.checkEditorial(blocker != "ui")
    assert requested.count() == 0
    if blocker == "playback":
        bridge._playback_binding = None


def test_social_invitation_persists_dismissal_and_only_opens_x_on_explicit_action(
    bridge, monkeypatch
):
    bridge._settings["social_invitation_dismissed"] = False
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    bridge._social_idle_since = qt_main.time.monotonic() - 9
    requested = QSignalSpy(bridge.socialInvitationRequested)
    opened = []
    monkeypatch.setattr(bridge, "openSocialAccount", lambda: opened.append(True))
    bridge.checkEditorial(True)
    bridge.checkEditorial(True)
    assert requested.count() == 1 and not opened
    bridge.dismissSocialInvitation(False)
    bridge.dismissSocialInvitation(True)
    assert not opened
    bridge._save_preferences()
    restarted = qt_main.Bridge(None)
    try:
        assert restarted._settings["social_invitation_dismissed"] is True
        repeated = QSignalSpy(restarted.socialInvitationRequested)
        restarted.checkEditorial(True)
        assert repeated.count() == 0
    finally:
        restarted.close()
    bridge._settings["social_invitation_dismissed"] = False
    bridge._social_idle_since = qt_main.time.monotonic() - 9
    bridge.checkEditorial(True)
    bridge.dismissSocialInvitation(True)
    assert opened == [True]


@pytest.mark.parametrize("width", [900, 1200])
def test_social_invitation_popup_fits_and_not_now_dismisses(bridge, width):
    bridge._settings["social_invitation_dismissed"] = False
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    bridge._social_idle_since = qt_main.time.monotonic() - 9
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.setWidth(width)
        settle()
        bridge.checkEditorial(True)
        settle(40)
        popup = window.findChild(QObject, "socialInvitationPopup")
        assert popup.property("visible")
        assert popup.property("width") <= window.width()
        assert popup.property("height") <= window.height()
        button = window.findChild(QObject, "socialInvitationLater")
        point = button.mapToItem(None, button.width() / 2, button.height() / 2)
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(point.x()), round(point.y())),
        )
        settle(40)
        assert not popup.property("visible")
        assert bridge._settings["social_invitation_dismissed"] is True
        assert window.findChild(QObject, "headerXButton").property("sceneIcon") == "x"
    finally:
        window.close()
        engine.deleteLater()
        settle()


def test_welcome_includes_optional_social_link_and_suppresses_upgrade_invitation(
    bridge, monkeypatch
):
    bridge._settings["social_invitation_dismissed"] = False
    opened = []
    monkeypatch.setattr(bridge, "openSocialAccount", lambda: opened.append(True))
    requested = QSignalSpy(bridge.socialInvitationRequested)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        assert bridge.openWelcome()
        settle(40)
        popup = window.findChild(QObject, "editorialPopup")
        button = window.findChild(QObject, "welcomeSocialFollow")
        assert popup.property("showSocialInvitation")
        assert button.isVisible() and not opened
        point = button.mapToItem(None, button.width() / 2, button.height() / 2)
        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(round(point.x()), round(point.y())),
        )
        assert opened == [True]
        popup.close()
        settle(40)
        bridge.checkEditorial(True)
        assert requested.count() == 0
        bridge._save_preferences()
        assert (
            load_settings(bridge._settings_path)["social_invitation_dismissed"] is True
        )
    finally:
        window.close()
        engine.deleteLater()
        settle()


def test_social_invitation_waits_eight_idle_seconds_and_input_resets_it(bridge):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent, QWindow

    bridge._settings["social_invitation_dismissed"] = False
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    requested = QSignalSpy(bridge.socialInvitationRequested)
    bridge.checkEditorial(True)
    assert requested.count() == 0
    bridge._social_idle_since = qt_main.time.monotonic() - 9
    window = QWindow()
    bridge.eventFilter(window, QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier))
    bridge.checkEditorial(True)
    assert requested.count() == 0
    bridge._social_idle_since = qt_main.time.monotonic() - 9
    bridge.checkEditorial(True)
    assert requested.count() == 1
    bridge.dismissSocialInvitation(False)


def test_actual_fresh_profile_uses_one_welcome_and_no_upgrade_invitation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    owner = qt_main.Bridge(None)
    try:
        assert owner._engagement.welcome_pending
        social = QSignalSpy(owner.socialInvitationRequested)
        owner.checkEditorial(True)
        assert owner.compactWelcome
        assert len(owner.editorialSlides) == 1
        assert owner.editorialFinishLabel == "Get started"
        owner.dismissEditorial(False)
        owner._save_preferences()
        owner._social_idle_since = qt_main.time.monotonic() - 9
        owner.checkEditorial(True)
        assert social.count() == 0
    finally:
        owner.close()
