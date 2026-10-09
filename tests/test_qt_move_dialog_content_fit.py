"""Content fit and dismissal semantics of the existing shared file-action popup."""

import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QPointF
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch


@pytest.fixture
def file_dialog(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    window.resize(820, 560)
    bridge._files.action = "move"
    bridge._files.phase = "preview"
    bridge._files.plan = SimpleNamespace(counts={"ready": 1}, items=())
    bridge._files.status = "One saved media item is ready to move."
    bridge.fileActionChanged.emit()
    popup = window.findChild(QObject, "libraryFileActionPopup")
    popup.open()
    QTest.qWait(100)
    yield app, bridge, window, popup
    _close(bridge, engine, window)


def relative_top(item, popup):
    return item.mapToItem(popup.property("contentItem"), QPointF(0, 0)).y()


def test_short_confirmation_has_no_stretch_gap_and_cancel_only_dismisses(file_dialog):
    _app, bridge, window, popup = file_dialog
    body = window.findChild(QObject, "fileActionBodyScroll")
    dismiss = window.findChild(QObject, "fileActionDismissButton")
    confirm = window.findChild(QObject, "fileActionConfirmButton")
    assert dismiss.property("label") == "Cancel"
    assert confirm.property("label") == "Move verified media"
    assert popup.property("height") < 210
    assert relative_top(dismiss, popup) - relative_top(
        body, popup
    ) - body.height() == pytest.approx(12)
    plan = bridge._files.plan
    dismiss.activated.emit()
    assert not popup.property("visible")
    assert bridge._files.plan is plan
    assert bridge._files.phase == "preview"
    assert bridge._files.worker is None


def test_completed_move_keeps_close_and_content_fit(file_dialog):
    _app, bridge, window, popup = file_dialog
    bridge._files.phase = "done"
    bridge._files.status = "Move complete. Library and media location updated."
    bridge.fileActionChanged.emit()
    QTest.qWait(80)
    assert popup.property("height") < 210
    assert (
        window.findChild(QObject, "fileActionDismissButton").property("label")
        == "Close"
    )
    assert not window.findChild(QObject, "fileActionConfirmButton").isVisible()


@pytest.mark.parametrize("lines", [8, 120])
def test_long_report_grows_then_scrolls_with_visible_footer(file_dialog, lines):
    _app, bridge, window, popup = file_dialog
    short_height = popup.property("height")
    bridge._files.status = "Verified saved media details retained for review.\n" * lines
    bridge.fileActionChanged.emit()
    # Text wrapping and nested layouts can require another polish cycle on a
    # busy hosted runner. Keep a bounded wait for the actual growth condition.
    deadline = time.monotonic() + 2
    while popup.property("height") <= short_height and time.monotonic() < deadline:
        QTest.qWait(20)
    assert popup.property("height") > short_height
    assert popup.property("height") <= window.height() - 40
    body = window.findChild(QObject, "fileActionBodyScroll")
    dismiss = window.findChild(QObject, "fileActionDismissButton")
    content = popup.property("contentItem")
    assert relative_top(dismiss, popup) >= relative_top(body, popup) + body.height()
    assert relative_top(dismiss, popup) + dismiss.height() <= content.height() + 0.1
    if lines == 120:
        scroll = body.property("contentItem")
        assert scroll.property("contentHeight") > scroll.height()
        scroll.setProperty(
            "contentY", scroll.property("contentHeight") - scroll.height()
        )
        QTest.qWait(50)
        assert scroll.property("contentY") > 0
        assert dismiss.isVisible()


@pytest.mark.parametrize(
    "action,phase,label,enabled",
    [
        ("delete", "preview", "Close", True),
        ("move", "recovery", "Close", True),
        ("move", "working", "Close", False),
    ],
)
def test_other_file_states_keep_existing_labels_and_busy_guard(
    file_dialog, action, phase, label, enabled
):
    _app, bridge, window, _popup = file_dialog
    bridge._files.action = action
    bridge._files.phase = phase
    bridge.fileActionChanged.emit()
    QTest.qWait(80)
    dismiss = window.findChild(QObject, "fileActionDismissButton")
    assert dismiss.property("label") == label
    assert dismiss.property("enabled") == enabled
