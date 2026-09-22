"""Caption safety fallback preserves actual track and deliberate view intent."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.playback_backend import MediaPlayerError
from yt_downloader.player_presentation_ui import PlayerPresentationMixin


def player(*, fill=True, track=-1):
    provider = SimpleNamespace(
        track=track,
        crop="fill" if fill else "fit",
        fail_layout=False,
        fail_track=False,
        fail_off=False,
        pause=Mock(),
    )

    def layout(**kwargs):
        if provider.fail_layout:
            raise MediaPlayerError("PRIVATE provider error")
        provider.crop = "fill" if kwargs["fill"] else "fit"

    def select(value):
        if provider.fail_track or (value == -1 and provider.fail_off):
            raise MediaPlayerError("PRIVATE caption error")
        provider.track = value

    provider.set_video_layout = Mock(side_effect=layout)
    provider.select_caption_track = Mock(side_effect=select)
    provider.selected_caption_track = lambda: provider.track
    state = SimpleNamespace(
        _closed=False,
        _video_fill=fill,
        _display_signature=None,
        _surface_owner=SimpleNamespace(
            stage=SimpleNamespace(winfo_width=lambda: 1380, winfo_height=lambda: 418)
        ),
        playback=provider,
        status_var=Mock(),
        _on_feature=Mock(),
        _on_operation=Mock(),
        _presentation_mode="embedded",
        _presentation_window=None,
    )
    state._apply_video_layout = PlayerPresentationMixin._apply_video_layout.__get__(
        state
    )
    return state, provider


def action(state, value):
    PlayerPresentationMixin._run_overlay_action(state, value, None)


@pytest.mark.parametrize("initial", [False, True])
def test_caption_enable_uses_fit_before_selecting_track_and_off_restores_fill(initial):
    state, provider = player(track=1 if initial else -1)
    if initial:
        PlayerPresentationMixin._synchronize_caption_layout(state)
    else:
        action(state, "caption:1")
    assert provider.crop == "fit" and provider.track == 1
    assert state._captions_active and not state._video_fill
    assert state._caption_restore_fill
    action(state, "caption:-1")
    assert provider.crop == "fill" and provider.track == -1 and state._video_fill
    assert not state._caption_restore_fill
    assert "caption_fill_restored" in [
        call.args[0] for call in state._on_feature.call_args_list
    ]


def test_explicit_fit_while_captions_active_is_not_undone_on_caption_off():
    state, provider = player()
    action(state, "caption:1")
    action(state, "fit")
    action(state, "caption:2")
    action(state, "caption:-1")
    assert provider.crop == "fit" and not state._video_fill


def test_initial_deliberate_fit_remains_fit_after_caption_toggle():
    state, provider = player(fill=False)
    action(state, "caption:1")
    action(state, "caption:-1")
    assert provider.crop == "fit" and not state._video_fill


def test_track_changes_preserve_pending_fill_restoration():
    state, provider = player()
    action(state, "caption:1")
    action(state, "caption:2")
    assert (
        provider.track == 2 and provider.crop == "fit" and state._caption_restore_fill
    )
    action(state, "caption:-1")
    assert provider.crop == "fill"


def test_fit_failure_cannot_enable_captions():
    state, provider = player()
    provider.fail_layout = True
    action(state, "caption:1")
    provider.select_caption_track.assert_not_called()
    assert state._video_fill and provider.track == -1
    assert "captions_selected" not in [
        call.args[0] for call in state._on_feature.call_args_list
    ]
    dimensions = state._on_operation.call_args.kwargs["dimensions"]
    assert dimensions["playback_control_origin"] == "caption_safety"
    assert "PRIVATE" not in state._control_notice


def test_failed_caption_selection_restores_previous_fill_when_captions_are_off():
    state, provider = player()
    provider.fail_track = True
    action(state, "caption:1")
    assert provider.track == -1 and provider.crop == "fill" and state._video_fill


def test_failed_track_change_keeps_existing_captions_fitted():
    state, provider = player(track=1)
    provider.fail_track = True
    action(state, "caption:2")
    assert provider.track == 1 and provider.crop == "fit" and not state._video_fill


def test_failed_caption_off_does_not_restore_fill():
    state, provider = player()
    action(state, "caption:1")
    provider.fail_off = True
    action(state, "caption:-1")
    assert provider.track == 1 and provider.crop == "fit" and not state._video_fill


def test_restore_failure_keeps_truthful_full_view_and_does_not_retry_each_poll():
    state, provider = player()
    action(state, "caption:1")
    provider.fail_layout = True
    action(state, "caption:-1")
    assert provider.track == -1 and not state._video_fill and provider.crop == "fit"
    calls = provider.set_video_layout.call_count
    for _ in range(100):
        PlayerPresentationMixin._synchronize_caption_layout(state)
    assert provider.set_video_layout.call_count == calls
    assert (
        state._on_operation.call_args.kwargs["dimensions"]["playback_control_origin"]
        == "caption_restore"
    )


@pytest.mark.parametrize("disable_fails", [False, True])
def test_initial_caption_fit_failure_disables_or_pauses_without_poll_flood(
    disable_fails,
):
    state, provider = player(track=1)
    provider.fail_layout = True
    provider.fail_off = disable_fails
    for _ in range(100):
        PlayerPresentationMixin._synchronize_caption_layout(state)
    assert provider.select_caption_track.call_count == 1
    assert provider.pause.call_count == int(disable_fails)
    assert provider.track == (1 if disable_fails else -1)
    assert "PRIVATE" not in state._control_notice


@pytest.mark.parametrize("mode", ["embedded", "fullscreen", "floating"])
def test_caption_fit_survives_view_and_size_changes_without_restarting_provider(mode):
    state, provider = player()
    action(state, "caption:1")
    state._presentation_mode = mode
    state._surface_owner.stage.winfo_width = lambda: 720
    state._surface_owner.stage.winfo_height = lambda: 405
    assert state._apply_video_layout()
    assert provider.crop == "fit" and provider.track == 1
    action(state, "caption:-1")
    assert provider.crop == "fill"
    provider.pause.assert_not_called()


def test_fill_is_disabled_and_explained_while_provider_captions_are_active():
    state, provider = player()
    action(state, "caption:1")
    options = PlayerPresentationMixin._native_menu_entries(state, captions=False)
    fill = next(item for item in options if item[1] == "fill")
    assert not fill[3] and "captions off" in fill[0]
    action(state, "fill")
    assert provider.crop == "fit" and provider.track == 1


def test_success_notice_expires_but_failure_notice_remains(monkeypatch):
    from yt_downloader import player_presentation_ui as module

    state = SimpleNamespace(status_var=Mock())
    snapshot = SimpleNamespace(error="", volume_observation=None)
    monkeypatch.setattr(module.time, "monotonic", lambda: 10)
    PlayerPresentationMixin._set_control_notice(state, "Showing full video", seconds=3)
    monkeypatch.setattr(module.time, "monotonic", lambda: 14)
    assert PlayerPresentationMixin._native_status_message(state, snapshot) == ""
    PlayerPresentationMixin._set_control_notice(state, "Try again")
    assert (
        PlayerPresentationMixin._native_status_message(state, snapshot) == "Try again"
    )


def test_fill_restore_waits_for_actual_caption_off_readback():
    state, provider = player()
    action(state, "caption:1")
    provider.select_caption_track = Mock()  # accepted, provider still switching
    action(state, "caption:-1")
    assert provider.track == 1 and provider.crop == "fit"
    provider.track = -1
    PlayerPresentationMixin._synchronize_caption_layout(state)
    assert provider.crop == "fill" and state._video_fill


@pytest.mark.parametrize("initial_track", [-1, 1])
def test_pending_enabled_track_keeps_fit_through_transient_off_and_can_be_superseded(
    initial_track,
):
    state, provider = player()
    if initial_track >= 0:
        action(state, "caption:1")
    provider.select_caption_track = Mock(
        side_effect=lambda _track: setattr(provider, "track", -1)
    )
    action(state, "caption:2")
    for _ in range(30):
        PlayerPresentationMixin._synchronize_caption_layout(state)
    assert provider.crop == "fit" and state._caption_restore_fill
    fill = next(
        item
        for item in PlayerPresentationMixin._native_menu_entries(state, captions=False)
        if item[1] == "fill"
    )
    assert not fill[3]
    action(state, "fill")
    assert provider.crop == "fit"
    action(state, "caption:-1")
    assert provider.crop == "fill" and not state._caption_restore_fill


def test_delayed_track_acknowledgment_preserves_manual_fit_and_restore_intent():
    state, provider = player()
    action(state, "caption:1")
    provider.select_caption_track = Mock(
        side_effect=lambda _track: setattr(provider, "track", -1)
    )
    action(state, "caption:2")
    provider.track = 2
    PlayerPresentationMixin._synchronize_caption_layout(state)
    assert provider.crop == "fit" and state._caption_restore_fill
    assert "_caption_request" not in state.__dict__
    action(state, "fit")
    action(state, "caption:-1")
    assert provider.crop == "fit"


@pytest.mark.parametrize("poll", [False, True])
def test_optional_app_observation_failure_cannot_interrupt_caption_transaction(
    monkeypatch, poll
):
    from yt_downloader import app as app_module

    state, provider = player(track=1 if poll else -1)
    telemetry = Mock()
    telemetry.record_feature.side_effect = OSError("PRIVATE optional sink failure")
    app = SimpleNamespace(product_telemetry=telemetry)
    diagnosis = Mock()
    monkeypatch.setattr(app_module, "write_diagnostic", diagnosis)
    state._on_feature = lambda value: app_module.DownloaderApp._record_feature(
        app, "player", value
    )
    if poll:
        PlayerPresentationMixin._synchronize_caption_layout(state)
    else:
        action(state, "caption:1")
    assert provider.crop == "fit" and provider.track == 1
    assert state._caption_restore_fill
    action(state, "caption:-1")
    assert provider.crop == "fill"
    for _ in range(30):
        app_module.DownloaderApp._record_feature(app, "player", "captions_selected")
    assert diagnosis.call_count == 3
    assert all(
        call.args == ("Optional feature observation could not be recorded.",)
        for call in diagnosis.call_args_list
    )
    state._on_operation.assert_not_called()
    telemetry.record_feature.side_effect = None
    app_module.DownloaderApp._record_feature(app, "player", "captions_selected")
    telemetry.record_feature.assert_called_with(
        "player", "captions_selected", dimensions=None
    )
