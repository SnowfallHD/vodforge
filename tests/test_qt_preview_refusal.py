"""A preview the link box can't start says why, where the user can see it.

Production 0.2.6 Windows: "Preview metadata" in Settings was pressed while the
link box was empty. The refusal message went to the notice under the link box,
which the open Settings window covers, so the button seemed to do nothing, and
telemetry reported the refusal as an unknown failure.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject

from tests.test_presentation_diagnostics import real_owner
from tests.test_qt_telemetry_coverage import rows
from tests.test_qt_update_check_guidance import update_click, update_notice_scene
from yt_downloader.download_service import ProviderNetworkCoordinator
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick import metadata_preview as preview_module

__all__ = ["update_notice_scene"]

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize(
    "link",
    [
        "",
        "   ",
        "youtube.com/watch?v=abcdefghijk",
        "https://www.youtube.com/playlist?list=PLPRIVATE",
    ],
)
def test_refused_link_is_reported_as_input_not_unknown(tmp_path, monkeypatch, link):
    telemetry = real_owner(tmp_path / "telemetry")
    preview = preview_module.QtMetadataPreview(ProviderNetworkCoordinator())
    preview.product_telemetry = telemetry
    monkeypatch.setattr(
        preview_module,
        "fetch_metadata_preview",
        lambda *_a, **_k: pytest.fail("a refused link must not reach the provider"),
    )
    try:
        assert not preview.begin(
            link,
            qt_main.OutputType.MP4,
            ignore_playlists=True,
            cookie_source=qt_main.CookieSource.PUBLIC,
            cookie_file=None,
            cookie_browser=None,
            ffmpeg=None,
            deno=None,
        )
        assert preview.message
        actual = rows(telemetry, tmp_path, "library_action_operation")
        assert [row["action"] for row in actual] == ["requested", "rejected"]
        assert actual[-1]["failure_reason"] == "invalid_input"
        assert actual[-1]["failure_detail"]["stage"] == "preparation"
    finally:
        preview.close()
        telemetry.shutdown(2)


def test_settings_preview_with_empty_box_shows_why(update_notice_scene):
    app, _bridge, window = update_notice_scene
    url_box = window.findChild(QObject, "forgeUrlInput")
    url_box.setProperty("text", "")
    update_click(window, window.findChild(QObject, "headerSettingsButton"))
    settings = window.findChild(QObject, "downloadSettingsPopup")
    assert settings.property("visible")
    update_click(window, window.findChild(QObject, "settingsPreviewMetadataButton"))
    app.processEvents()
    assert not settings.property("visible")
    notice = window.findChild(QObject, "operationNotice")
    assert notice.property("visible")
    assert notice.property("message") == "Paste a complete video URL first."
    assert url_box.property("activeFocus")


@pytest.mark.parametrize("button", ["analyticsDecline", "analyticsAccept"])
def test_analytics_choice_that_cannot_be_saved_says_so(
    update_notice_scene, monkeypatch, button
):
    """Same flaw in the first-run analytics pop-up: a failed save's message went
    behind the pop-up, and the pop-up stayed open with buttons that did nothing."""
    app, bridge, window = update_notice_scene
    monkeypatch.setattr(bridge._analytics, "choose", lambda _enabled: False)
    bridge.analyticsPromptRequested.emit()
    app.processEvents()
    popup = window.findChild(QObject, "analyticsConsentPopup")
    assert popup.property("visible")
    update_click(window, window.findChild(QObject, button))
    app.processEvents()
    assert not popup.property("visible")
    notice = window.findChild(QObject, "operationNotice")
    assert notice.property("visible")
    assert "could not be saved" in notice.property("message")
