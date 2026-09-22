"""Transition ownership, optional observation and navigation ordering."""

from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

from yt_downloader.ui_transition import ViewTransition, cancel_view_transition


def prepared_transition(monkeypatch):
    from PIL import ImageTk

    from yt_downloader import ui_transition

    root = Mock()
    frame = Mock()
    frame.winfo_width.return_value = 100
    frame.winfo_height.return_value = 80
    monkeypatch.setattr(
        ui_transition,
        "capture_own_widget",
        lambda _: Image.new("RGB", (100, 80), "#234567"),
    )
    monkeypatch.setattr(ImageTk, "PhotoImage", lambda *_a, **_kw: object())
    monkeypatch.setattr(ui_transition.tk, "Label", lambda *_a, **_kw: Mock())
    transition = ViewTransition(root)
    transition.prepare(frame)
    return root, frame, transition


def test_replacement_retires_timer_and_old_callback_cannot_remove_new_cover(
    monkeypatch,
):
    root, frame, transition = prepared_transition(monkeypatch)
    transition.reveal(frame)
    old_generation, old_timer, overlay = (
        transition._generation,
        transition._timer,
        transition._overlay,
    )
    transition.prepare(frame)
    root.after_cancel.assert_called_with(old_timer)
    overlay.destroy.assert_called_once()
    replacement = transition._overlay
    transition.reveal(frame)
    transition._finish(old_generation)
    assert transition._overlay is replacement and transition._target is frame


def test_unprepared_reveal_cannot_blur_already_visible_destination():
    root = Mock()
    transition = ViewTransition(root)
    transition.reveal(Mock())
    root.after.assert_not_called()
    assert transition._overlay is None and transition._target is None


def test_within_view_navigation_retires_pending_reveal_and_images(monkeypatch):
    root, frame, transition = prepared_transition(monkeypatch)
    root._view_transition = transition
    transition.reveal(frame)
    cancel_view_transition(SimpleNamespace(winfo_toplevel=lambda: root))
    assert transition._timer is None and transition._target is None
    assert transition._image is None


def test_optional_transition_observations_are_content_free_bounded_and_isolated():
    observed = Mock(side_effect=RuntimeError("unavailable"))
    transition = ViewTransition(Mock(), observed=observed)
    for _ in range(100):
        transition._observe("transition_shown")
        transition._observe("transition_skipped")
    assert observed.call_count == 2


def test_player_release_precedes_old_capture_and_new_tab_reveal():
    from yt_downloader.app import DownloaderApp

    order = []
    host = object()
    transition = SimpleNamespace(
        cancel=lambda: order.append("cancel-overlay"),
        prepare=lambda _: order.append("prepare-old-view"),
        reveal=lambda _: order.append("reveal-new-tab"),
    )
    view = SimpleNamespace(
        _focus_selected_view="watch",
        _view_transition=transition,
        _focus_views={"watch": Mock(), "library": Mock()},
        _focus_nav_buttons={},
        _focus_nav_icons={},
        _focus_nav_underlines={},
        _archive_overlay=host,
        _archive_player_origin="watch",
        _archive_playback_host=host,
        _archive_cancel_playback=lambda: order.append("release-player"),
        _record_feature=Mock(),
        _apply_focus_layout=Mock(),
        _queue_focus_selected_overview_layout=Mock(),
        _queue_quality_e2e_library_visibility_receipt=Mock(),
    )
    DownloaderApp._select_focus_view(view, "library")
    assert order == [
        "cancel-overlay",
        "release-player",
        "prepare-old-view",
        "reveal-new-tab",
    ]
    assert view._focus_selected_view == "library"


def test_destroyed_source_is_not_captured(monkeypatch):
    from yt_downloader import ui_transition

    capture = Mock()
    monkeypatch.setattr(ui_transition, "capture_own_widget", capture)
    transition = ViewTransition(Mock())
    frame = Mock(winfo_exists=Mock(return_value=False))
    transition.prepare(frame)
    capture.assert_not_called()
    frame.winfo_ismapped.assert_not_called()


def test_owner_destroy_cancels_timer_and_late_callbacks_cannot_restore_overlay(
    monkeypatch,
):
    root, frame, transition = prepared_transition(monkeypatch)
    transition.reveal(frame)
    generation, timer = transition._generation, transition._timer
    transition._destroyed(SimpleNamespace(widget=frame))
    root.after_cancel.assert_called_with(timer)
    transition._finish(generation)
    assert transition._timer is None and transition._overlay is None
    transition._destroyed(SimpleNamespace(widget=root))
    assert transition._image is None and transition._target is None


def test_destination_drawing_precedes_reveal_and_reentrant_replacement_wins(
    monkeypatch,
):
    from yt_downloader import ui_transition

    _root, frame, transition = prepared_transition(monkeypatch)
    observed = []
    replacement = object()

    def draw(target):
        assert transition._overlay is not None and target is frame
        observed.append(target)
        transition.cancel()
        transition._overlay = replacement

    monkeypatch.setattr(ui_transition, "present_pending_drawing", draw, raising=False)
    transition.reveal(frame)
    transition._finish(transition._generation)
    assert observed == [frame]
    assert transition._overlay is replacement


def test_destination_without_child_canvas_is_drawn_before_reveal(monkeypatch):
    from yt_downloader import ui_transition

    _root, frame, transition = prepared_transition(monkeypatch)
    frame.winfo_children.return_value = []
    observed = []

    def draw(target):
        assert transition._overlay is not None
        observed.append(target)

    monkeypatch.setattr(ui_transition, "present_pending_drawing", draw, raising=False)
    transition.reveal(frame)
    transition._finish(transition._generation)
    assert observed == [frame], "A leaf-widget destination must not bypass drawing"
    assert transition._overlay is None


def test_pending_drawing_yields_with_cover_and_finishes_within_three_passes(
    monkeypatch,
):
    from yt_downloader import ui_transition

    root, frame, transition = prepared_transition(monkeypatch)
    draw = Mock(side_effect=[False, False, True])
    monkeypatch.setattr(ui_transition, "present_pending_drawing", draw)
    transition.reveal(frame)
    cover, generation = transition._overlay, transition._generation
    transition._finish(generation)
    assert transition._overlay is cover
    assert root.after.call_args.args[0] == 8
    root.after.call_args.args[1]()
    assert transition._overlay is cover
    root.after.call_args.args[1]()
    assert draw.call_count == 3
    assert transition._overlay is None and transition._timer is None


def test_continuously_pending_drawing_cannot_keep_cover_indefinitely(monkeypatch):
    from yt_downloader import ui_transition

    root, frame, transition = prepared_transition(monkeypatch)
    draw = Mock(return_value=False)
    monkeypatch.setattr(ui_transition, "present_pending_drawing", draw)
    transition.reveal(frame)
    generation = transition._generation
    transition._finish(generation)
    assert transition._overlay is not None
    for _ in range(2):
        root.after.call_args.args[1]()
    assert draw.call_count == 3
    assert transition._overlay is None and transition._timer is None
    transition._finish(generation)
    assert draw.call_count == 3


def test_cancel_between_drawing_passes_retires_queued_completion(monkeypatch):
    from yt_downloader import ui_transition

    root, frame, transition = prepared_transition(monkeypatch)
    draw = Mock(return_value=False)
    monkeypatch.setattr(ui_transition, "present_pending_drawing", draw)
    transition.reveal(frame)
    transition._finish(transition._generation)
    queued = root.after.call_args.args[1]
    transition.cancel()
    queued()
    assert draw.call_count == 1
    assert transition._overlay is None and transition._timer is None


def test_cover_press_reveals_without_forwarding_to_an_unseen_owner(monkeypatch):
    root, frame, transition = prepared_transition(monkeypatch)
    transition.reveal(frame)
    assert transition._pointer(SimpleNamespace(x_root=40, y_root=40)) == "break"
    assert transition._overlay is None and transition._timer is None
    root.winfo_containing.assert_not_called()


def test_transition_optional_touchpad_absence_keeps_pointer_wheel_and_retirement(
    monkeypatch,
):
    import tkinter as tk

    from PIL import ImageTk

    from yt_downloader import ui_transition

    root, frame, overlay = Mock(), Mock(), Mock()
    frame.winfo_width.return_value = 100
    frame.winfo_height.return_value = 80

    def unsupported(*args):
        if len(args) == 4 and args[2] == "<TouchpadScroll>" and args[3]:
            raise tk.TclError('bad event type or keysym "TouchpadScroll"')
        return ""

    overlay.tk.call.side_effect = unsupported
    monkeypatch.setattr(
        ui_transition, "capture_own_widget", lambda _: Image.new("RGB", (100, 80))
    )
    monkeypatch.setattr(ImageTk, "PhotoImage", lambda *_a, **_kw: object())
    monkeypatch.setattr(ui_transition.tk, "Label", lambda *_a, **_kw: overlay)
    transition = ViewTransition(root)
    transition.prepare(frame)
    assert {call.args[0] for call in overlay.bind.call_args_list} == {
        "<ButtonPress-1>",
        "<MouseWheel>",
    }
    transition.cancel()
    overlay.destroy.assert_called_once()
    assert transition._overlay is None
