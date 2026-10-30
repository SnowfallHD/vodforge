"""Picker startup ordering against actual human retreat packets; no native pixel claim."""

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject
from PySide6.QtTest import QTest

from tests.test_qt_header_native_clock import publish
from tests.test_qt_native_header_modal_boundary import child_header  # noqa: F401


def test_picker_waits_for_retreat_and_coalesces_repeat_request(child_header):  # noqa: F811
    _app, _bridge, main, _header, _child, _boundary = child_header
    rows = json.loads(
        (
            Path(__file__).parent / "fixtures/mac_picker_retreat_20261023.json"
        ).read_text()
    )
    times = ["16:56:33.006926", "16:56:34.242304", "16:56:34.286726", "16:56:35.216047"]
    rows = [next(x for x in rows if t in x["utc"]) for t in times]
    phases = []
    main.setProperty("pickerTimelineEnabled", True)
    main.pickerTimelinePhase.connect(phases.append)
    try:
        for i, row in enumerate(rows[:3], 1):
            publish(main, row, i)
        QMetaObject.invokeMethod(main, "openOutputFolderDialog")
        QMetaObject.invokeMethod(main, "openOutputFolderDialog")
        assert 3 not in phases, "native open began in the recorded retreat"
        publish(main, rows[3], 4)
        QTest.qWait(130)
        assert phases.count(3) == 1
    finally:
        dialog = main.findChild(QObject, "outputFolderDialog")
        if dialog:
            QMetaObject.invokeMethod(dialog, "close")


@pytest.mark.parametrize("finish", ["deadline", "hidden_geometry_still_moving"])
def test_pending_picker_is_bounded_and_waits_for_hidden_geometry_quiet(
    child_header,  # noqa: F811
    finish,
):
    _app, _bridge, main, _header, _child, _boundary = child_header
    rows = json.loads(
        (
            Path(__file__).parent / "fixtures/mac_picker_retreat_20261023.json"
        ).read_text()
    )
    rows = [
        next(x for x in rows if t in x["utc"])
        for t in ["16:56:33.006926", "16:56:34.286726", "16:56:35.216047"]
    ]
    phases = []
    main.setProperty("pickerTimelineEnabled", True)
    main.pickerTimelinePhase.connect(phases.append)
    try:
        publish(main, rows[0], 1)
        publish(main, rows[1], 2)
        QMetaObject.invokeMethod(main, "openOutputFolderDialog")
        assert 3 not in phases
        if finish == "deadline":
            QTest.qWait(1120)
        else:
            hidden = dict(rows[2], packet_host=[10, 842, 1422, 44])
            publish(main, hidden, 3)
            QTest.qWait(45)
            publish(main, rows[2], 4)
            QTest.qWait(45)
            assert 3 not in phases, (
                "picker opened while hidden native geometry was still moving"
            )
            QTest.qWait(70)
        assert phases.count(3) == 1
    finally:
        dialog = main.findChild(QObject, "outputFolderDialog")
        if dialog:
            QMetaObject.invokeMethod(dialog, "close")


def test_settled_windowed_picker_opens_without_added_wait(child_header):  # noqa: F811
    _app, _bridge, main, _header, _child, _boundary = child_header
    row = json.loads(
        (Path(__file__).parent / "fixtures/mac_header_reveal_88c122e.json").read_text()
    )["rows"][0]
    phases = []
    main.setProperty("pickerTimelineEnabled", True)
    main.pickerTimelinePhase.connect(phases.append)
    try:
        publish(main, row, 1)
        QMetaObject.invokeMethod(main, "openOutputFolderDialog")
        assert phases.count(3) == 1
    finally:
        dialog = main.findChild(QObject, "outputFolderDialog")
        if dialog:
            QMetaObject.invokeMethod(dialog, "close")


@pytest.mark.parametrize("transition", [1, 2])
@pytest.mark.parametrize("fullscreen_end", [False, True])
def test_picker_waits_for_fullscreen_transition_end(
    child_header, transition, fullscreen_end  # noqa: F811
):
    _app, _bridge, main, _header, _child, _boundary = child_header
    row = json.loads(
        (Path(__file__).parent / "fixtures/mac_header_reveal_88c122e.json").read_text()
    )["rows"][0]
    row = dict(row, packet_transition=transition)
    if fullscreen_end:
        row.update(
            packet_content=[0, 0, 1440, 900],
            packet_host=[10, 852, 1422, 44],
            target_x=99,
            packet_state="controls-visible",
        )
    phases = []
    main.setProperty("pickerTimelineEnabled", True)
    main.pickerTimelinePhase.connect(phases.append)
    try:
        publish(main, row, 1)
        QMetaObject.invokeMethod(main, "openOutputFolderDialog")
        QTest.qWait(120)
        assert 3 not in phases, (
            "native picker began while fullscreen transition was active"
        )
        publish(main, dict(row, packet_transition=0), 2)
        QTest.qWait(130)
        assert phases.count(3) == 1
    finally:
        dialog = main.findChild(QObject, "outputFolderDialog")
        if dialog:
            QMetaObject.invokeMethod(dialog, "close")
