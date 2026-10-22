"""Bounded packet-driven trajectories, not actual macOS animation acceptance."""

import copy
import json

import pytest
from PySide6.QtTest import QTest

from tests.test_mac_header_packet import entered
from tests.test_qt_native_header_modal_boundary import child_header  # noqa: F401
from yt_downloader.qt_quick.mac_header_packet import NativeRowRefused, packet


@pytest.mark.parametrize("bad", ["outside", "not-containing", "reorder"])
def test_current_full_control_bounds_remain_independently_validated(bad):
    sample = entered()
    for button in sample["buttons"]:
        button["screen_bounds"] = list(button["visible_screen"])
    if bad == "outside":
        sample["buttons"][0]["screen_bounds"][0] = -1
    elif bad == "not-containing":
        sample["buttons"][0]["screen_bounds"][2] = 1
    else:
        sample["buttons"][0]["screen_bounds"][2] = 40
    with pytest.raises(NativeRowRefused):
        packet(sample, 44, 1, 20)


def test_interrupted_reveal_and_aperture_settle_have_no_second_animation(
    child_header,  # noqa: F811
    tmp_path,
):
    _app, _bridge, main, header, _child, _boundary = child_header
    sample = entered()
    for button in sample["buttons"]:
        button["screen_bounds"] = list(button["visible_screen"])
    records = []
    sequence = 0

    def publish(visible, host=10):
        nonlocal sequence
        sequence += 1
        current = copy.deepcopy(sample)
        current["host"][0] = host
        current["host"][2] = 1440 - host
        if not visible:
            for button in current["buttons"]:
                button.update(visibility="hidden", visible_screen=[0, 0, 0, 0])
        main.setProperty("nativeRowPacket", packet(current, 44, sequence, 20))

    def observe(label):
        current = main.property("nativeRowPacket")
        records.append(
            {
                "label": label,
                "host_x": current["host_screen"][0],
                "target_x": current["content_target_screen_x"],
                "animated_x": header.property("nativeContentScreenX"),
                "rendered_x": current["host_screen"][0]
                + header.property("nativeHeaderInset"),
            }
        )

    for cycle in range(2):
        publish(False)
        QTest.qWait(100)
        publish(True)
        QTest.qWait(60)
        assert 0 < header.property("nativeContentScreenX") < 99
        observe("moving-right")
        publish(False)
        QTest.qWait(25)
        observe("reversed-left")
        publish(True)
        QTest.qWait(280)
        assert header.property("nativeContentScreenX") == 99
        publish(True, 102)
        observe("native-aperture-overrun")
        assert header.property("nativeContentScreenX") == 99
        publish(True, 96)
        for _ in range(10):
            observe("aperture-settled")
            QTest.qWait(20)
            assert header.property("nativeContentScreenX") == 99
            assert header.property("nativeHeaderInset") == 3
    (tmp_path / "trajectory.json").write_text(json.dumps(records, indent=2))


def test_atomic_native_sample_exposes_full_bounds_without_new_native_getters():
    from yt_downloader.platforms.macos.header_host import HeaderHost, Snapshot

    row = Snapshot()
    row.flags = 1 | 8 | 16
    row.hostVisible = 1
    row.geometry[27:31] = [10, 852, 1422, 44]
    row.geometry[62:66] = [0, 0, 1440, 900]
    for i in range(3):
        row.buttons[i] = i + 1
        row.visibility[i] = 1
        row.visible[i * 4 : i * 4 + 4] = [19 + 23 * i, 867, 8, 14]
        row.geometry[37 + i * 10 : 41 + i * 10] = [19 + 23 * i, 867, 14, 14]
    host = HeaderHost.__new__(HeaderHost)
    host._row = row
    sample = host.row_sample()
    assert sample["buttons"][2]["screen_bounds"] == [65, 867, 14, 14]
    assert packet(sample, 44, 1, 20)["content_target_screen_x"] == 99


def test_retirement_drops_native_screen_origin_without_replaying_motion(child_header):  # noqa: F811
    import sys

    _app, _bridge, main, header, _child, _boundary = child_header
    sample = entered()
    sample["host"][0] += 100
    sample["content"][0] += 100
    for button in sample["buttons"]:
        button["visible_screen"][0] += 100
    main.setProperty("nativeRowPacket", packet(sample, 44, 1, 20))
    QTest.qWait(40)
    assert header.property("nativeContentScreenX") == 199
    main.setProperty("nativeHeaderAttached", False)
    expected = 82 if sys.platform == "darwin" else 0
    for _ in range(12):
        assert header.property("nativeContentScreenX") == expected
        QTest.qWait(20)


def test_full_button_partly_offscreen_uses_current_visible_clip_without_retirement():
    sample = entered()
    for button in sample["buttons"]:
        button["screen_bounds"] = list(button["visible_screen"])
    sample["buttons"][0].update(
        screen_bounds=[-4, 867, 14, 14], visible_screen=[0, 867, 10, 14]
    )
    assert packet(sample, 44, 1, 20)["content_target_screen_x"] == 99
