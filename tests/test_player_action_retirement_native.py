"""Player input retirement with real widgets and a controlled playback provider."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import make_backend, pump

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="native display required",
)


@pytest.mark.parametrize("close_mode", ["close", "external_destroy"])
@pytest.mark.parametrize(
    "action", ["seek", "relative", "timeline", "chapter", "preview", "volume"]
)
def test_player_retired_input_cannot_touch_widgets_or_provider(
    application,
    tmp_path,
    monkeypatch,
    close_mode,
    action,
):
    from yt_downloader.media_player_ui import MediaPlayerWindow

    app = application
    backend, module = make_backend()
    media = tmp_path / "controlled.mp4"
    media.write_bytes(b"controlled provider; no actual playback claim")
    backend.load(media, duration=100)
    features = []
    provider_calls = []
    for name in ("seek", "set_volume"):
        original = getattr(backend, name)

        def invoke(*args, _name=name, _original=original, **kwargs):
            provider_calls.append((_name, args))
            return _original(*args, **kwargs)

        monkeypatch.setattr(backend, name, invoke)
    player = MediaPlayerWindow(
        app,
        playback=backend,
        previews=SimpleNamespace(
            preview_png=lambda _position: None, shutdown=lambda: None
        ),
        info={
            "title": "Controlled chapters",
            "chapters": [
                {"title": "Opening", "start_time": 0, "end_time": 30},
                {"title": "Second chapter", "start_time": 30, "end_time": 100},
            ],
        },
        on_feature=lambda feature, **fields: features.append((feature, fields)),
    )
    try:
        # Valid control reaches the actual provider before this owner's retirement.
        player._seek_to(25)
        assert provider_calls[-1] == ("seek", (25,))
        assert any(feature == "seek" for feature, _fields in features)
        assert player.chapter_list is not None
        player.chapter_list.selection_set("1")
        pump(app, 0.1)
        callback = {
            "seek": lambda: player._seek_to(50),
            "relative": lambda: player._seek_relative(10),
            "timeline": lambda: player._timeline_clicked(SimpleNamespace(x=50, y=10)),
            "chapter": lambda: player._chapter_selected(SimpleNamespace()),
            "preview": lambda: player._seek_preview(0),
            "volume": lambda: player._schedule_volume("60"),
        }[action]
        live_count = len(provider_calls)
        callback()
        assert len(provider_calls) == live_count + 1, "Live input must reach playback"
        if close_mode == "close":
            player.close()
        else:
            player.popup.destroy()
        pump(app, 0.1)
        assert player._closed
        assert module.player.release_calls == 1
        before_calls = tuple(provider_calls)
        before_features = tuple(features)
        # Model already-dispatched input whose Python callback outlives its widgets.
        callback()
        assert tuple(provider_calls) == before_calls, "Retired input reached playback"
        assert tuple(features) == before_features, "Retired input emitted a feature"
    finally:
        player.close()
        pump(app, 0.05)


@pytest.mark.parametrize("replacement", ["different_path", "same_path", "backend"])
@pytest.mark.parametrize("action", ["seek", "timeline", "chapter", "preview"])
def test_player_media_bound_input_cannot_target_successor(
    application,
    tmp_path,
    monkeypatch,
    replacement,
    action,
):
    from yt_downloader.media_player_ui import MediaPlayerWindow

    backend, _module = make_backend()
    media = tmp_path / "original.mp4"
    media.write_bytes(b"controlled provider")
    backend.load(media, duration=100)
    features = []
    player = MediaPlayerWindow(
        application,
        playback=backend,
        previews=SimpleNamespace(
            preview_png=lambda _position: None, shutdown=lambda: None
        ),
        info={
            "title": "Original media",
            "chapters": [
                {"title": "Original chapter", "start_time": 30, "end_time": 100},
            ],
        },
        on_feature=lambda feature, **fields: features.append((feature, fields)),
    )
    current = backend
    try:
        assert player.chapter_list is not None
        player.chapter_list.selection_set("0")
        pump(application, 0.05)
        callback = {
            "seek": lambda: player._seek_to(50),
            "timeline": lambda: player._timeline_clicked(SimpleNamespace(x=50, y=10)),
            "chapter": lambda: player._chapter_selected(SimpleNamespace()),
            "preview": lambda: player._seek_preview(0),
        }[action]
        # Original bound intent is valid before the replacement.
        callback()
        if replacement == "backend":
            current, _successor_module = make_backend()
            player.playback = current
        target = media
        if replacement == "different_path":
            target = tmp_path / "successor.mp4"
            target.write_bytes(b"controlled successor")
        current.load(target, duration=200)
        if action == "chapter":
            player.chapter_list.destroy()
        elif action == "timeline":
            player.timeline.destroy()
        calls = []
        original = current.seek

        def seek(position):
            calls.append(position)
            return original(position)

        monkeypatch.setattr(current, "seek", seek)
        baseline_features = tuple(features)
        # These coordinates/times belong to the original view's media.
        callback()
        assert not calls, "Captured media intent targeted the successor"
        assert tuple(features) == baseline_features
        # Keyboard transport is deliberately current-media intent.
        player._seek_relative(10)
        assert len(calls) == 1
    finally:
        player.close()
        if current is not backend:
            backend.shutdown()
        pump(application, 0.05)
