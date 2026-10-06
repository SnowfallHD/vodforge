"""Closing retained playback refreshes Watch without replacing it while paused."""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QSignalSpy

from tests.test_qt_library_section_selection import library as library_fixture
from yt_downloader.playback_backend import PlaybackSnapshot
from yt_downloader.playback_progress_binding import PlaybackProgressBinding

library = library_fixture


def attach(bridge, record):
    """Use the real progress lifetime with deterministic provider snapshots."""
    bridge._playback_generation += 1
    bridge._playback_path = Path(record["vodforge_output_path"])
    bridge._playback_record = record
    bridge._playback_status = "Ready"
    bridge._playback_position = 0
    bridge._playback_duration = 100
    bridge._playback_binding = PlaybackProgressBinding(
        bridge._playback_progress,
        record,
        snapshot=bridge._playback_snapshot(),
        seek=bridge._request_playback_seek,
    )
    return bridge._playback_generation


def projection(scene):
    value = scene.property("projection")
    return value.toVariant() if hasattr(value, "toVariant") else value


@pytest.mark.parametrize("close_from", ["Watch", "Library"])
def test_close_refreshes_latest_hero_and_preserves_resume_and_route(
    library, close_from
):
    app, bridge, window, _ = library
    first, second = bridge._runtime.history[:2]
    ledger = bridge._playback_progress
    session = ledger.begin(first)
    ledger.observe(
        session,
        PlaybackSnapshot(Path(first["vodforge_output_path"]), "Playing", 15, 100, 80),
    )
    ledger.retire(session)
    bridge.select("Watch")
    app.processEvents()
    scene = window.findChild(QObject, "watchBrowseScene")
    assert projection(scene)["hero"]["title"] == first["title"]
    generation = attach(bridge, second)
    bridge.observePlayback(35, 100, "Playing", generation)
    bridge.observePlayback(37, 100, "Paused", generation)
    app.processEvents()
    assert projection(scene)["hero"]["title"] == first["title"]
    bridge.select(close_from)
    app.processEvents()
    changed = QSignalSpy(bridge.watchSceneChanged)
    binding = bridge._playback_binding
    bridge.closePlayback(True)
    app.processEvents()
    assert bridge.selection == close_from
    assert changed.count() == 1
    assert ledger.resume_position(second) == 37
    bridge.observePlayback(99, 100, "Ended", generation)
    binding.present(
        PlaybackSnapshot(Path(second["vodforge_output_path"]), "Playing", 99, 100, 80)
    )
    assert ledger.resume_position(second) == 37
    bridge.closePlayback(True)
    assert changed.count() == 1
    bridge.select("Watch")
    app.processEvents()
    assert projection(scene)["hero"]["title"] == second["title"]
    assert bridge.watchHeroProgress(projection(scene)["hero"]["owner"])["resume"]


def test_rapid_new_playback_rejects_old_provider_and_binding_updates(library):
    app, bridge, window, _ = library
    first, second = bridge._runtime.history[:2]
    bridge.select("Watch")
    old_generation = attach(bridge, first)
    bridge.observePlayback(20, 100, "Playing", old_generation)
    old_binding = bridge._playback_binding
    bridge.closePlayback(True)
    bridge.select("Library")
    generation = attach(bridge, second)
    bridge.observePlayback(45, 100, "Playing", generation)
    bridge.observePlayback(99, 100, "Ended", old_generation)
    old_binding.close()
    old_binding.present(
        PlaybackSnapshot(Path(first["vodforge_output_path"]), "Playing", 99, 100, 80)
    )
    assert bridge._playback_progress.resume_position(first) == 20
    assert bridge._playback_progress.resume_position(second) == 45
    bridge.closePlayback(True)
    bridge.select("Watch")
    app.processEvents()
    scene = window.findChild(QObject, "watchBrowseScene")
    assert projection(scene)["hero"]["title"] == second["title"]
