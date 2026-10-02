"""One player clock, independent caption controls, stale-worker ownership."""

import threading
import time

import pytest
from PySide6.QtCore import Property, QObject, Signal

from tests.test_qt_floating_player_chrome import player_scene  # noqa: F401
from tests.test_qt_player_hover_aspect import flush
from tests.test_qt_scene_port import saved
from yt_downloader.qt_quick.subtitle_session import SubtitleSession
from yt_downloader.subtitle_cues import Cue, CueTimeline


@pytest.mark.parametrize("mode", ["embedded", "floating", "fullscreen"])
def test_independent_controls_share_clock_across_surfaces(player_scene, mode):  # noqa: F811
    app, window, scene, _ = player_scene
    bridge = scene.property("appBridge")
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Fictional", "MP4"
    )
    bridge.playerSceneChanged.emit()
    bridge.select("Watch")
    session = bridge._subtitles
    session.catalog = {
        "original": {"index": 2},
        "translations": [{"index": 5, "label": "Spanish", "language": "es"}],
    }
    session.cues = {
        "original": CueTimeline((Cue(0, 2000, "Original"),)),
        "translation": CueTimeline((Cue(0, 2000, "Translated"),)),
    }
    session.changed.emit()

    class Clock(QObject):
        changed = Signal()
        position = Property(int, lambda self: self.value, notify=changed)
        duration = Property(int, lambda self: 10000, constant=True)
        activeSubtitleTrack = Property(int, lambda self: -1, constant=True)
        playbackState = Property(int, lambda self: 2, constant=True)

        def __init__(self):
            super().__init__()
            self.value = 500

    clock = Clock()
    scene.setProperty("player", clock)
    scene.setProperty("presentationMode", mode)
    scene.setProperty("visible", True)
    window.findChild(QObject, "watchBrowseScene").setProperty("visible", False)
    flush(app)
    prefix = "player" if mode == "embedded" else "presentation"
    overlay = window.findChild(
        QObject,
        "embeddedPlayerOverlay" if mode == "embedded" else "presentationPlayerOverlay",
    )
    overlay.setProperty("surfaceHovered", True)
    flush(app)
    window.findChild(QObject, prefix + "CaptionsButton").activated.emit()
    flush(app)
    assert session.enabled
    assert not window.findChild(QObject, prefix + "CaptionsMenu").property("visible")
    window.findChild(QObject, prefix + "SubtitlesButton").activated.emit()
    flush(app)
    assert window.findChild(QObject, prefix + "CaptionsMenu").property("visible")
    # Simulate actual menu's stream-index request without another media player.
    session.selected = 5
    session.changed.emit()
    flush(app)
    text = window.findChild(
        QObject,
        "embeddedCaptionText" if mode == "embedded" else "presentationCaptionText",
    )
    assert text.property("text") == "Original\n\nTranslated"
    window.findChild(QObject, prefix + "CaptionsButton").activated.emit()
    flush(app)
    assert text.property("text") == "Translated"
    assert session.selected == 5
    clock.value = 2000
    clock.changed.emit()
    flush(app)
    assert text.property("text") == ""
    clock.value = 1000
    clock.changed.emit()
    flush(app)
    assert text.property("text") == "Translated"
    assert scene.property("player") is clock
    assert clock.property("playbackState") == 2


def test_unavailable_controls_are_truthful_and_new_owner_resets(player_scene):  # noqa: F811
    app, window, scene, _ = player_scene
    session = scene.property("appBridge")._subtitles
    flush(app)
    assert not window.findChild(QObject, "playerCaptionsButton").property("enabled")
    assert not window.findChild(QObject, "playerSubtitlesButton").property("enabled")
    session.enabled, session.selected = True, 3
    session.load(None)
    flush(app)
    assert not session.enabled and session.selected == -1
    assert not scene.property("captionsActive")


def test_stale_results_never_retarget_new_owner_or_selected_stream():
    session = SubtitleSession(None)
    old = threading.Event()
    session.requests["original"] = old
    session.load(None)
    session._accept(
        (session.generation - 1, "original", old, (Cue(0, 1000, "OLD"),), False)
    )
    assert not session.cues
    current = threading.Event()
    replaced = threading.Event()
    session.requests["translation"] = current
    session._accept(
        (session.generation, "translation", replaced, (Cue(0, 1000, "WRONG"),), False)
    )
    assert not session.cues


def test_changed_file_result_rejected_and_worker_cancelled(
    tmp_path,
    monkeypatch,
    player_scene,  # noqa: F811
):
    app, _, _, _ = player_scene
    media = tmp_path / "fictional.mp4"
    media.write_bytes(b"original")
    started, finish = threading.Event(), threading.Event()

    def probe(*args):
        started.set()
        finish.wait(2)
        return {"original": {"index": 1}, "translations": []}

    monkeypatch.setattr(
        "yt_downloader.qt_quick.subtitle_session.probe_saved_subtitles", probe
    )
    session = SubtitleSession("existing-tool")
    session.load(media)
    assert started.wait(1)
    media.write_bytes(b"replaced-file")
    finish.set()
    deadline = time.monotonic() + 2
    while session.loading and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not session.state["originalAvailable"]
    assert session.message == "Saved captions unavailable"


def test_failed_read_retries_without_changing_other_renderer():
    session = SubtitleSession(None)
    session.catalog = {"original": {"index": 1}, "translations": [{"index": 2}]}
    session.enabled = True
    session.cues["original"] = CueTimeline((Cue(0, 2000, "Original"),))
    session.selected = 2
    request = threading.Event()
    session.requests["translation"] = request
    session._accept((session.generation, "translation", request, None, True))
    assert session.enabled and session.selected == -1
    assert session.textAt(500) == {"original": "Original", "translation": ""}
    assert "Try again" in session.message
    assert session.textAt(float("nan")) == {"original": "", "translation": ""}
