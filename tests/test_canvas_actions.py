"""Pointer gestures must never follow a repaint or leak into a modal."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader import ui_canvas_actions
from yt_downloader.ui_canvas_actions import CanvasActions


def fixture(monkeypatch):
    monkeypatch.setattr(ui_canvas_actions, "paint_action_material", Mock())
    canvas = Mock(
        grab_current=Mock(return_value=None), canvasx=lambda x: x, canvasy=lambda y: y
    )
    action = Mock()
    targets = [((0, 0, 40, 40), action)]
    owner = CanvasActions(canvas, lambda: targets)
    return owner, targets, action, SimpleNamespace(x=20, y=20)


def test_action_runs_once_on_release_and_never_on_press(monkeypatch):
    owner, _, action, event = fixture(monkeypatch)
    assert owner.press(event) == "break"
    action.assert_not_called()
    assert owner.release(event) == "break"
    owner.release(event)
    action.assert_called_once_with()


@pytest.mark.parametrize("change", ["repaint", "navigate", "modal", "outside"])
def test_release_cannot_follow_changed_render_or_input_owner(monkeypatch, change):
    owner, targets, action, event = fixture(monkeypatch)
    owner.press(event)
    if change == "repaint":
        targets[:] = [(targets[0][0], Mock())]
    elif change == "navigate":
        targets.clear()
    elif change == "modal":
        owner.canvas.grab_current.return_value = object()
    else:
        event.x = 80
    owner.release(event)
    action.assert_not_called()
    if targets and change == "repaint":
        targets[0][1].assert_not_called()


def test_nested_dispatch_cannot_reuse_the_gesture(monkeypatch):
    owner, _targets, action, event = fixture(monkeypatch)
    action.side_effect = lambda: owner.release(event)
    owner.press(event)
    owner.release(event)
    action.assert_called_once_with()


def test_topmost_control_owns_press_and_hover(monkeypatch):
    owner, targets, original, event = fixture(monkeypatch)
    overlay = Mock()
    targets.append(((10, 10, 30, 30), overlay))
    owner.motion(event)
    assert ui_canvas_actions.paint_action_material.call_args.args[1:] == (
        (10, 10, 30, 30),
        False,
    )
    owner.press(event)
    assert ui_canvas_actions.paint_action_material.call_args.args[1:] == (
        (10, 10, 30, 30),
        True,
    )
    owner.canvas.create_polygon.assert_not_called()
    owner.release(event)
    overlay.assert_called_once()
    original.assert_not_called()
