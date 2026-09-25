"""Provider capabilities and presentation lifetimes use the live playback owner."""

import sys
from collections import deque
from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_libvlc_backend import make_backend
from yt_downloader.playback_backend import MediaPlayerError
from yt_downloader.player_presentation_ui import PlayerPresentationMixin


@pytest.mark.skipif(sys.platform != "darwin", reason="AppKit overlay owner")
def test_player_control_hover_keeps_static_gradient_without_filled_state(monkeypatch):
    from yt_downloader.platforms.macos import player_overlay as native

    painted = []

    class Gradient:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithStartingColor_endingColor_(self, *_colors):
            return self

        def drawInRect_angle_(self, *_args):
            painted.append("static-gradient")

    class Path:
        @classmethod
        def bezierPathWithRoundedRect_xRadius_yRadius_(cls, *_args):
            return cls()

        def setLineWidth_(self, *_args):
            pass

        def stroke(self):
            painted.append("focus-stroke")

        def fill(self):
            painted.append("transient-fill")

    monkeypatch.setattr(native, "NSGradient", Gradient)
    monkeypatch.setattr(
        native,
        "NSColor",
        SimpleNamespace(colorWithCalibratedWhite_alpha_=lambda *_args: object()),
    )
    monkeypatch.setattr(native, "NSBezierPath", Path)
    monkeypatch.setattr(native, "_role_color", lambda *_args: Mock())
    view = native.VODForgePlayerOverlayView.alloc().initWithFrame_(((0, 0), (400, 110)))
    view.owner = SimpleNamespace(
        _control_highlights=((0, ((0, 0), (36, 36)), "hover", False),)
    )
    native.VODForgePlayerOverlayView.drawRect_(view, None)
    assert painted == ["static-gradient"]
    view.owner._control_highlights = ((0, ((0, 0), (36, 36)), "pressed", False),)
    native.VODForgePlayerOverlayView.drawRect_(view, None)
    assert painted == ["static-gradient", "static-gradient"]
    view.owner._control_highlights = ((0, ((0, 0), (36, 36)), "hover", True),)
    native.VODForgePlayerOverlayView.drawRect_(view, None)
    assert painted == [
        "static-gradient",
        "static-gradient",
        "static-gradient",
        "focus-stroke",
    ]


@pytest.mark.parametrize(
    "fill,size,expected",
    [
        (False, (1380, 418), ""),
        (True, (1380, 418), "1380:418"),
        (True, (1920, 1200), "1920:1200"),
        (True, (720, 405), "720:405"),
    ],
)
def test_video_crop_uses_actual_stage_and_fit_clears_crop(fill, size, expected):
    backend, module = make_backend()
    module.player.video_set_crop_geometry = Mock()
    backend.set_video_layout(fill=fill, width=size[0], height=size[1])
    module.player.video_set_crop_geometry.assert_called_once_with(expected)
    assert module.player.stop_calls == 0


@pytest.mark.parametrize("width,height", [(0, 10), (10, 0), (-1, 10)])
def test_invalid_stage_cannot_change_provider_crop(width, height):
    backend, module = make_backend()
    module.player.video_set_crop_geometry = Mock()
    with pytest.raises(MediaPlayerError):
        backend.set_video_layout(fill=True, width=width, height=height)
    module.player.video_set_crop_geometry.assert_not_called()


def test_crop_failure_is_reported_without_restarting_player():
    backend, module = make_backend()
    module.player.video_set_crop_geometry = Mock(side_effect=RuntimeError("provider"))
    with pytest.raises(MediaPlayerError, match="could not be changed"):
        backend.set_video_layout(fill=True, width=100, height=50)
    assert module.player.stop_calls == 0


def test_caption_choices_only_include_actual_provider_tracks_with_bounded_names():
    backend, module = make_backend()
    module.player.video_get_spu_description = lambda: [
        (-1, b"Disable"),
        (2, b"English"),
        (3, b"\xff" + b"a" * 300),
    ]
    tracks = backend.caption_tracks()
    assert tracks[0] == (2, "English")
    assert len(tracks) == 2 and len(tracks[1][1]) == 160


@pytest.mark.parametrize("track", [-1, 2])
def test_caption_selection_uses_real_track_id(track):
    backend, module = make_backend()
    module.player.video_get_spu_description = lambda: [(2, b"English")]
    module.player.video_set_spu = Mock(return_value=0)
    backend.select_caption_track(track)
    module.player.video_set_spu.assert_called_once_with(track)


def test_removed_caption_track_cannot_select_a_different_track():
    backend, module = make_backend()
    module.player.video_get_spu_description = lambda: [(2, b"English")]
    module.player.video_set_spu = Mock()
    with pytest.raises(MediaPlayerError, match="no longer available"):
        backend.select_caption_track(3)
    module.player.video_set_spu.assert_not_called()


def test_caption_provider_rejection_does_not_claim_success():
    backend, module = make_backend()
    module.player.video_set_spu = Mock(return_value=-1)
    with pytest.raises(MediaPlayerError, match="could not be changed"):
        backend.select_caption_track(-1)


@pytest.mark.parametrize("operation", ["caption_tracks", "selected_caption_track"])
def test_caption_lookup_failure_becomes_bounded_player_error(operation):
    backend, module = make_backend()
    module.player.video_get_spu_description = Mock(side_effect=RuntimeError("private"))
    module.player.video_get_spu = Mock(side_effect=RuntimeError("private"))
    with pytest.raises(MediaPlayerError) as error:
        getattr(backend, operation)()
    assert "private" not in str(error.value)


def test_closed_backend_cannot_apply_video_layout():
    backend, module = make_backend()
    backend.shutdown()
    module.player.video_set_crop_geometry = Mock()
    with pytest.raises(MediaPlayerError):
        backend.set_video_layout(fill=False, width=100, height=100)
    module.player.video_set_crop_geometry.assert_not_called()


def test_native_delegate_only_queues_and_never_enters_tk():
    state = SimpleNamespace(
        _closed=False,
        _overlay_actions=deque(),
        popup=Mock(),
        _run_overlay_action=Mock(),
    )
    PlayerPresentationMixin._dispatch_overlay_action(state, "toggle", None)
    assert list(state._overlay_actions) == [("toggle", None)]
    state.popup.assert_not_called()
    assert not state.popup.mock_calls
    state._run_overlay_action.assert_not_called()
    PlayerPresentationMixin._drain_overlay_actions(state)
    state._run_overlay_action.assert_called_once_with("toggle", None)


def test_retired_delegate_and_queued_action_cannot_run_after_close():
    state = SimpleNamespace(
        _closed=True,
        _overlay_actions=deque([("toggle", None)]),
        _run_overlay_action=Mock(),
    )
    PlayerPresentationMixin._dispatch_overlay_action(state, "toggle", None)
    PlayerPresentationMixin._drain_overlay_actions(state)
    state._run_overlay_action.assert_not_called()
    assert len(state._overlay_actions) == 1


def test_native_seek_gesture_is_coalesced_and_pending_queue_is_bounded():
    state = SimpleNamespace(_closed=False, _overlay_actions=deque())
    for value in range(1000):
        PlayerPresentationMixin._dispatch_overlay_action(
            state, "seek_fraction", value / 1000
        )
    assert list(state._overlay_actions) == [("seek_fraction", 0.999)]
    for _ in range(1000):
        PlayerPresentationMixin._dispatch_overlay_action(state, "toggle", None)
    assert len(state._overlay_actions) == 64


def test_close_discards_native_dispatch_before_releasing_overlay():
    events = []
    state = SimpleNamespace(_overlay_actions=deque([("toggle", None)]))
    state._native_overlay = SimpleNamespace(
        close=lambda: events.append(tuple(state._overlay_actions))
    )
    PlayerPresentationMixin._close_native_controls(state)
    assert events == [()]
    assert not state._overlay_actions and state._native_overlay is None
    PlayerPresentationMixin._close_native_controls(state)
    assert len(events) == 1


def test_failed_fill_choice_restores_previous_mode_without_success_event():
    state = SimpleNamespace(
        _closed=False,
        _video_fill=False,
        _display_signature=None,
        _surface_owner=SimpleNamespace(
            stage=SimpleNamespace(winfo_width=lambda: 100, winfo_height=lambda: 50)
        ),
        playback=SimpleNamespace(
            set_video_layout=Mock(side_effect=MediaPlayerError("private"))
        ),
        status_var=Mock(),
        _on_feature=Mock(),
    )
    state._apply_video_layout = PlayerPresentationMixin._apply_video_layout.__get__(
        state
    )
    PlayerPresentationMixin._run_overlay_action(state, "fill", None)
    assert state._video_fill is False
    state._on_feature.assert_called_once_with("control_failed")


def test_return_rehosts_live_surface_before_destroying_presentation_window():
    events = []
    surface = SimpleNamespace(
        rehost=lambda top, stage: events.append(("rehost", top, stage))
    )
    window = SimpleNamespace(destroy=lambda: events.append("destroy"))
    state = SimpleNamespace(
        _closed=False,
        _surface_owner=surface,
        _presentation_window=window,
        _presentation_mode="floating",
        stage="embedded-stage",
        popup=SimpleNamespace(
            winfo_toplevel=lambda: "main-window", focus_set=lambda: None
        ),
        _native_surface_changed=lambda: events.append("sync"),
        _on_feature=Mock(),
    )
    PlayerPresentationMixin._return_presentation(state)
    assert events == [("rehost", "main-window", "embedded-stage"), "sync", "destroy"]
    assert state._surface_owner is surface
    assert state._presentation_window is None
    assert state._presentation_mode == "embedded"
    state._on_feature.assert_called_once_with("returned")


@pytest.mark.parametrize("action", ["fit", "fill"])
def test_display_choice_reports_only_after_provider_application(action):
    from yt_downloader.telemetry_features import FEATURE_ACTIONS

    events = []
    state = SimpleNamespace(
        _closed=False,
        _video_fill=False,
        _apply_video_layout=lambda **kwargs: events.append("applied") or True,
        _on_feature=lambda name, **fields: events.append((name, fields)),
    )
    PlayerPresentationMixin._run_overlay_action(state, action, None)
    assert events == ["applied", (action, {})]
    assert action in FEATURE_ACTIONS["player"]


@pytest.mark.parametrize("failed", [False, True])
def test_caption_producer_never_sends_track_id_or_private_label(failed):
    from yt_downloader.telemetry_features import FEATURE_ACTIONS

    events = []
    provider = Mock(side_effect=MediaPlayerError("unavailable") if failed else None)
    state = SimpleNamespace(
        _closed=False,
        playback=SimpleNamespace(select_caption_track=provider),
        _on_feature=lambda action, **fields: events.append((action, fields)),
        status_var=Mock(),
    )
    PlayerPresentationMixin._run_overlay_action(state, "caption:92", None)
    provider.assert_called_once_with(92)
    assert events == (
        [("control_failed", {})] if failed else [("captions_selected", {})]
    )
    if events:
        assert events[0][0] in FEATURE_ACTIONS["player"]


def test_poll_does_not_schedule_again_if_presentation_closes_player():
    from yt_downloader.media_player_ui import MediaPlayerWindow

    state = SimpleNamespace(
        _closed=False,
        playback=SimpleNamespace(snapshot=object()),
        popup=Mock(),
        _poll=Mock(),
    )
    state._present_snapshot = lambda snapshot: setattr(state, "_closed", True)
    MediaPlayerWindow._poll(state)
    state.popup.after.assert_not_called()


def test_failed_queued_action_does_not_stop_later_control_dispatch(caplog):
    events = []
    state = SimpleNamespace(
        _closed=False,
        _overlay_actions=deque([("fullscreen", None), ("toggle", None)]),
        _on_feature=Mock(),
        status_var=Mock(),
    )

    def run(action, value):
        if action == "fullscreen":
            raise RuntimeError("private native detail")
        events.append(action)

    state._run_overlay_action = run
    PlayerPresentationMixin._drain_overlay_actions(state)
    assert events == ["toggle"] and not state._draining_overlay_actions
    state._on_feature.assert_called_once_with("control_failed")
    assert "private" not in repr(state.status_var.mock_calls)
    assert "private native detail" in caplog.text


def test_nested_native_drain_cannot_dispatch_an_action_twice():
    events = []
    state = SimpleNamespace(
        _closed=False, _overlay_actions=deque([("first", None), ("second", None)])
    )

    def run(action, value):
        events.append(action)
        PlayerPresentationMixin._drain_overlay_actions(state)

    state._run_overlay_action = run
    PlayerPresentationMixin._drain_overlay_actions(state)
    assert events == ["first", "second"] and not state._draining_overlay_actions


def test_native_controls_render_failure_notice_in_visible_overlay():
    state = SimpleNamespace(
        _closed=False,
        _overlay_actions=deque(),
        _native_overlay=Mock(),
        _presentation_mode="embedded",
        _control_notice="That playback option is unavailable right now.",
        time_var=SimpleNamespace(get=lambda: "0:10 / 1:00"),
        playback=SimpleNamespace(
            caption_tracks=lambda: (), selected_caption_track=lambda: -1
        ),
        _video_fill=True,
        _presentation_window=None,
    )
    state._native_menu_entries = PlayerPresentationMixin._native_menu_entries.__get__(
        state
    )
    snapshot = SimpleNamespace(error="", volume_observation=None)
    PlayerPresentationMixin._present_native_controls(state, snapshot)
    assert (
        state._native_overlay.present.call_args.kwargs["notice"]
        == state._control_notice
    )
    assert state._native_overlay.set_menus.call_args.args[1] == [
        ("No captions in this video", "", False, False)
    ]


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("progress", "Saved position is unavailable"),
        ("provider", "The local media file could not be played."),
        ("volume", "Volume is unavailable"),
    ],
)
def test_native_status_preserves_provider_progress_and_volume_failures(kind, expected):
    state = SimpleNamespace()
    snapshot = SimpleNamespace(error="", volume_observation=None)
    if kind == "progress":
        state._progress_binding = SimpleNamespace(notice=expected)
    elif kind == "provider":
        snapshot.error = expected
    else:
        snapshot.volume_observation = SimpleNamespace(disposition="failed")
    assert PlayerPresentationMixin._native_status_message(state, snapshot) == expected


@pytest.mark.parametrize(
    "token,closed,expected",
    [
        ("7|caption:92", False, [("caption:92", None)]),
        ("6|caption:92", False, []),
        ("7|caption:92", True, []),
        ("7|", False, []),
        (None, False, []),
    ],
)
def test_native_menu_item_retains_action_and_rejects_retired_generation(
    token, closed, expected
):
    from yt_downloader.platforms.macos.player_overlay import MacOSPlayerOverlay

    events = []
    state = SimpleNamespace(
        _closed=closed,
        _menu_generation=7,
        dispatch=lambda action, value: events.append((action, value)),
    )
    MacOSPlayerOverlay.dispatch_menu(state, token)
    assert events == expected


@pytest.mark.parametrize("width", [480, 500, 679, 680, 720, 980, 1414, 1920])
def test_actual_overlay_layout_keeps_time_and_controls_separate(monkeypatch, width):
    from yt_downloader.platforms.macos import player_overlay as module

    class Item:
        def __init__(self):
            self.frame = None
            self.hidden = False

        def setFrame_(self, frame):
            self.frame = frame

        def setHidden_(self, value):
            self.hidden = value

        def setNeedsDisplay_(self, value):
            pass

    frame = SimpleNamespace(
        origin=SimpleNamespace(x=0, y=0), size=SimpleNamespace(width=width, height=418)
    )
    parent = SimpleNamespace(addSubview_positioned_relativeTo_=lambda *args: None)
    native = SimpleNamespace(frame=lambda: frame, superview=lambda: parent)
    state = SimpleNamespace(
        _closed=False,
        surface=SimpleNamespace(macos_view=native),
        view=Item(),
        video_click=Item(),
        timeline=Item(),
        buttons=[Item() for _ in range(8)],
        time=Item(),
        volume=Item(),
        notice=Item(),
    )
    monkeypatch.setattr(module, "NSWindowAbove", 1, raising=False)
    module.MacOSPlayerOverlay.sync(state)
    items = [*state.buttons, state.time, state.volume]
    spans = sorted(
        (item.frame[0][0], item.frame[0][0] + item.frame[1][0])
        for item in items
        if not item.hidden
    )
    assert all(0 <= left < right <= width for left, right in spans)
    assert all(a[1] <= b[0] for a, b in pairwise(spans))
    assert state._time_width >= 94


def test_direct_application_destroy_retires_browser_restoration_before_tk_teardown(
    monkeypatch,
):
    import tkinter as tk

    from yt_downloader.app import DownloaderApp

    state = DownloaderApp.__new__(DownloaderApp)
    state._closing = False
    observed = []
    monkeypatch.setattr(tk.Tk, "destroy", lambda self: observed.append(self._closing))
    state.destroy()
    assert observed == [True]


@pytest.mark.parametrize(
    "case",
    [
        "control_fit",
        "control_fill",
        "control_captions",
        "control_fullscreen",
        "control_caption_safety",
        "control_caption_restore",
    ],
)
def test_actual_control_failure_producer_preserves_operation_and_excludes_private_text(
    tmp_path, case
):
    import json

    from quality_harness.playback_probe import CONTROL_EXPECTATIONS, run_case

    calls = []
    owner = SimpleNamespace(
        record_operation=lambda *args, **fields: calls.append((args, fields))
    )
    result = run_case(tmp_path, owner, case)
    failures = [
        fields
        for args, fields in calls
        if args == ("playback_operation", "control_failed")
    ]
    assert len(failures) == 1
    event = failures[0]
    assert event["dimensions"]["playback_origin"] == "watch"
    assert event["dimensions"]["playback_view"] == "embedded"
    assert event["dimensions"]["playback_control"] == CONTROL_EXPECTATIONS[case][0]
    assert (
        event["dimensions"]["playback_control_origin"] == CONTROL_EXPECTATIONS[case][1]
    )
    assert event["dimensions"]["control_failure_kind"] == (
        "unexpected_error" if case == "control_fullscreen" else "provider_error"
    )
    detail = event["failure_detail"].payload()
    assert detail["os_error"] == 5
    assert detail["source_module"] in {"libvlc_backend", "player_presentation_ui"}
    assert detail["source_scope"] == "first_party_frame"
    assert "PRIVATE" not in json.dumps(detail)
    operation_keys = {fields["operation_key"] for _, fields in calls}
    assert len(operation_keys) == 1
    assert result["actions"][-1] == "closed"


def test_control_failure_observation_is_bounded_without_blocking_later_actions():
    state = SimpleNamespace(_on_feature=Mock(), _on_operation=Mock())
    error = RuntimeError("PRIVATE")
    for _ in range(200):
        PlayerPresentationMixin._report_control_failure(state, "caption:private", error)
    assert state._on_operation.call_count == 8
    assert state._on_feature.call_count == 8
    assert (
        state._on_operation.call_args.kwargs["dimensions"]["playback_control"]
        == "captions"
    )


def test_broken_optional_control_observers_do_not_break_error_handling():
    state = SimpleNamespace(
        _on_feature=Mock(side_effect=RuntimeError("usage observer")),
        _on_operation=Mock(side_effect=RuntimeError("operation observer")),
    )
    PlayerPresentationMixin._report_control_failure(
        state, "private input", RuntimeError()
    )
    assert (
        state._on_operation.call_args.kwargs["dimensions"]["playback_control"]
        == "unknown"
    )


def test_automatic_layout_failure_does_not_flood_user_control_diagnostics():
    state = SimpleNamespace(
        _video_fill=True,
        _display_signature=None,
        _surface_owner=SimpleNamespace(
            stage=SimpleNamespace(winfo_width=lambda: 100, winfo_height=lambda: 50)
        ),
        playback=SimpleNamespace(
            set_video_layout=Mock(side_effect=MediaPlayerError("private"))
        ),
        status_var=Mock(),
        _on_feature=Mock(),
        _on_operation=Mock(),
    )
    for _ in range(100):
        assert not PlayerPresentationMixin._apply_video_layout(state)
    state._on_operation.assert_not_called()
    assert "private" not in state._control_notice


@pytest.mark.parametrize(
    "playing,notice,inside,over_controls,interacting,expected",
    [
        (True, "", True, False, False, False),
        (False, "", True, False, False, True),
        (True, "Readable problem", True, False, False, True),
        (True, "", True, True, False, True),
        (True, "", True, False, True, True),
        (True, "", False, False, False, False),
    ],
)
def test_controls_hide_only_when_playback_can_remain_unattended(
    playing,
    notice,
    inside,
    over_controls,
    interacting,
    expected,
):
    from yt_downloader.platforms.macos.player_overlay import MacOSPlayerOverlay

    state = SimpleNamespace(
        _closed=False,
        _last_interaction=0,
        _pointer_position=(20, 200),
        _controls_visible=True,
        _visibility_events=0,
        _on_action=Mock(),
    )
    result = MacOSPlayerOverlay._update_visibility(
        state,
        playing=playing,
        notice=notice,
        pointer=(20, 200),
        inside=inside,
        over_controls=over_controls,
        interacting=interacting,
        now=4,
    )
    assert result is expected
    assert state._on_action.call_count == (0 if expected else 1)


def test_pointer_motion_wakes_controls_without_a_seek_or_timer():
    from yt_downloader.platforms.macos.player_overlay import MacOSPlayerOverlay

    state = SimpleNamespace(
        _closed=False,
        _last_interaction=0,
        _pointer_position=(20, 200),
        _controls_visible=False,
        _visibility_events=0,
        _on_action=Mock(),
    )
    assert MacOSPlayerOverlay._update_visibility(
        state,
        playing=True,
        notice="",
        pointer=(21, 200),
        inside=True,
        over_controls=False,
        interacting=False,
        now=10,
    )
    state._on_action.assert_called_once_with("controls_shown", None)
    assert state._last_interaction == 10


def test_repeated_motion_outside_video_does_not_wake_controls():
    from yt_downloader.platforms.macos.player_overlay import MacOSPlayerOverlay

    state = SimpleNamespace(
        _closed=False,
        _last_interaction=0,
        _pointer_position=(20, 200),
        _controls_visible=False,
        _visibility_events=0,
        _on_action=Mock(),
    )
    for offset in range(100):
        assert not MacOSPlayerOverlay._update_visibility(
            state,
            playing=True,
            notice="",
            pointer=(-20, offset),
            inside=False,
            over_controls=False,
            interacting=False,
            now=10,
        )
    state._on_action.assert_not_called()


def test_visibility_observations_are_bounded_and_stop_at_close():
    from yt_downloader.platforms.macos.player_overlay import MacOSPlayerOverlay

    state = SimpleNamespace(
        _closed=False,
        _last_interaction=0,
        _pointer_position=(20, 200),
        _controls_visible=True,
        _visibility_events=0,
        _on_action=Mock(),
    )
    for index in range(100):
        MacOSPlayerOverlay._update_visibility(
            state,
            playing=index % 2 == 0,
            notice="",
            pointer=(20, 200),
            inside=True,
            over_controls=False,
            interacting=False,
            now=10 + index * 4,
        )
    assert state._on_action.call_count == 8
    state._closed = True
    assert not MacOSPlayerOverlay._update_visibility(
        state,
        playing=False,
        notice="",
        pointer=(21, 200),
        inside=True,
        over_controls=False,
        interacting=False,
        now=1000,
    )
    assert state._on_action.call_count == 8


def test_visibility_observation_preserves_control_failure_notice():
    state = SimpleNamespace(
        _closed=False, _control_notice="Please try again", _on_feature=Mock()
    )
    PlayerPresentationMixin._run_overlay_action(state, "controls_shown", None)
    assert state._control_notice == "Please try again"
    state._on_feature.assert_called_once_with("controls_shown")


@pytest.mark.parametrize(
    "host,audio,expected_focus",
    [(object(), False, False), (object(), True, True), (None, False, True)],
)
def test_queue_host_show_does_not_focus_background_embedded_window(
    host, audio, expected_focus
):
    from yt_downloader.media_player_ui import MediaPlayerWindow

    state = SimpleNamespace(
        _closed=False,
        _shown_once=False,
        embedded=True,
        popup=Mock(),
        _initial_presentation_host=host,
        _audio_only=audio,
        _poll=Mock(),
        _autoplay=False,
    )
    MediaPlayerWindow.show(state)
    assert state.popup.focus_set.called is expected_focus
    state._poll.assert_called_once_with()


@pytest.mark.skipif(sys.platform != "darwin", reason="AppKit overlay owner")
def test_native_control_state_adapter_is_shared_and_retires_disabled_hover(monkeypatch):
    from yt_downloader.platforms.macos import player_overlay as native

    pointer = SimpleNamespace(x=5, y=5)
    window = Mock()
    window.firstResponder.return_value = None
    view = Mock()
    view.window.return_value = window
    view.convertPoint_fromView_.return_value = pointer
    view.isHidden.return_value = False
    controls = []
    for x in (0, 40):
        control = Mock()
        control.frame.return_value = SimpleNamespace(
            origin=SimpleNamespace(x=x, y=0), size=SimpleNamespace(width=30, height=30)
        )
        control.isEnabled.return_value = True
        control.isHidden.return_value = False
        control.alphaValue.return_value = 1.0
        control.isDescendantOf_.return_value = False
        controls.append(control)
    event = SimpleNamespace(pressedMouseButtons=lambda: 0)
    monkeypatch.setattr(native, "NSEvent", event, raising=False)
    state = SimpleNamespace(
        view=view, buttons=[controls[0]], volume=controls[1], _control_highlights=()
    )
    native.MacOSPlayerOverlay._paint_control_states(state)
    assert [(item[0], item[2]) for item in state._control_highlights] == [(0, "hover")]
    event.pressedMouseButtons = lambda: 1
    native.MacOSPlayerOverlay._paint_control_states(state)
    assert state._control_highlights[0][2] == "pressed"
    controls[0].isEnabled.return_value = False
    native.MacOSPlayerOverlay._paint_control_states(state)
    assert state._control_highlights == ()
    controls[0].setAlphaValue_.assert_called_with(0.38)
    pointer.x = 100
    window.firstResponder.return_value = controls[1]
    native.MacOSPlayerOverlay._paint_control_states(state)
    assert state._control_highlights[0][0] == 1 and state._control_highlights[0][3]
    view.isHidden.return_value = True
    native.MacOSPlayerOverlay._paint_control_states(state)
    assert state._control_highlights == ()
