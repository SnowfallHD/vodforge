from pathlib import Path

import pytest

from yt_downloader.qt_quick.mac_header_packet import NativeRowRefused, packet

BASE = Path(__file__).resolve().parent


def entered():
    return {
        "owner": "unified-toolbar",
        "current": True,
        "host_visible": True,
        "toolbar_owned": True,
        "delegate_unchanged": True,
        "full_size": True,
        "transparent": True,
        "title_hidden": True,
        "transition": 0,
        "fullscreen": True,
        "host": [10.0, 852.0, 1422.0, 44.0],
        "host_allocated": True,
        "content": [0.0, 0.0, 1440.0, 900.0],
        "buttons": [
            {
                "identity": 503346145024,
                "visibility": "visible",
                "visible_screen": [19.0, 867.0, 14.0, 14.0],
            },
            {
                "identity": 503346148096,
                "visibility": "visible",
                "visible_screen": [42.0, 867.0, 14.0, 14.0],
            },
            {
                "identity": 503346146560,
                "visibility": "visible",
                "visible_screen": [65.0, 867.0, 14.0, 14.0],
            },
        ],
    }


def test_actual_fullscreen_controls_inside_item_have_current_clearance():
    s = entered()
    p = packet(s, 44, 1)
    right = max(b["visible_screen"][0] + b["visible_screen"][2] for b in s["buttons"])
    assert p["leading"] == right - s["host"][0] and p["reserve"] == p["leading"]
    assert p["host_screen"] == s["host"] and p["body_slot_height"] == 44


def test_actual_windowed_adjacent_controls_keep_zero_inset():
    s = {
        "owner": "unified-toolbar",
        "current": True,
        "host_visible": True,
        "toolbar_owned": True,
        "delegate_unchanged": True,
        "full_size": True,
        "transparent": True,
        "title_hidden": True,
        "transition": 0,
        "fullscreen": False,
        "host": [126.0, 822.0, 996.0, 44.0],
        "host_allocated": True,
        "content": [30.0, 130.0, 1100.0, 740.0],
        "buttons": [
            {
                "identity": 503346145024,
                "visibility": "visible",
                "visible_screen": [49.0, 837.0, 14.0, 14.0],
            },
            {
                "identity": 503346148096,
                "visibility": "visible",
                "visible_screen": [72.0, 837.0, 14.0, 14.0],
            },
            {
                "identity": 503346146560,
                "visibility": "visible",
                "visible_screen": [95.0, 837.0, 14.0, 14.0],
            },
        ],
        "accessories_empty": True,
        "content_screen": [30.0, 130.0, 1100.0, 740.0],
    }
    p = packet(s, 44, 1)
    assert p["leading"] == p["reserve"] == 0


def test_hidden_controls_do_not_retain_overlap_clearance():
    s = entered()
    for b in s["buttons"]:
        b.update(visibility="hidden", visible_screen=[0, 0, 0, 0])
    p = packet(s, 44, 2)
    assert p["leading"] == p["reserve"] == 0 and p["body_slot_height"] == 44


def test_height_and_actual_control_ownership_refusals_stay_strict():
    for error in ["short", "mixed", "identity", "vertical", "outside"]:
        s = entered()
        if error == "short":
            s["host"][3] = 32
        if error == "mixed":
            s["buttons"][0]["visibility"] = "hidden"
        if error == "identity":
            s["buttons"][1]["identity"] = s["buttons"][0]["identity"]
        if error == "vertical":
            s["buttons"][0]["visible_screen"][1] += 100
        if error == "outside":
            s["buttons"][0]["visible_screen"][0] = -100
        with pytest.raises(NativeRowRefused):
            packet(s, 44, 1)


def test_visible_control_clearance_has_one_target_through_native_reallocation():
    # Native06 exposed a backward target step at the overlap boundary. Use the
    # same current controls with each actual item position, never cached width.
    import copy

    sample = entered()
    right = max(
        b["visible_screen"][0] + b["visible_screen"][2] for b in sample["buttons"]
    )
    sample["fullscreen"] = True
    targets = []
    for x in (sample["host"][0], right - 2, right + 3, right + 17):
        current = copy.deepcopy(sample)
        current["host"][2] -= x - current["host"][0]
        current["host"][0] = x
        row = packet(current, 44, 1, 20)
        targets.append(row["host_screen"][0] + row["leading"])
    assert targets == [right + 20] * 4


@pytest.mark.parametrize("transition", [1, 2])
def test_authoritative_inflight_native_row_is_not_a_stale_settled_packet(transition):
    s = entered()
    s["transition"] = transition
    p = packet(s, 44, 1, 20)
    assert p["host_screen"] == s["host"]
    assert p["width"] == s["host"][2]


def test_hidden_native_overlay_during_reparenting_keeps_geometry_without_claiming_visibility():
    s = entered()
    s.update(transition=1, host_visible=False)
    for button in s["buttons"]:
        button.update(visibility="hidden", visible_screen=[0, 0, 0, 0])
    p = packet(s, 44, 1, 20)
    assert p["host_screen"] == s["host"] and p["host_visible"] is False
    s["transition"] = 0
    with pytest.raises(NativeRowRefused):
        packet(s, 44, 2, 20)
