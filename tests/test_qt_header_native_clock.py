"""Replay measured AppKit allocations; this is not new native pixel acceptance."""

import json
from pathlib import Path

import pytest
from PySide6.QtTest import QTest

from tests.test_qt_native_header_modal_boundary import child_header  # noqa: F401


def publish(main, row, sequence):
    fullscreen = row["packet_content"][2] == 1440
    main.setProperty(
        "nativeRowPacket",
        {
            "schema_version": 1,
            "sequence": sequence,
            "host_screen": row["packet_host"],
            "content_screen": row["packet_content"],
            "content_target_screen_x": row["target_x"],
            "state": row["packet_state"],
            "fullscreen": fullscreen,
            "transition": row["packet_transition"],
            "height": 44,
            "width": row["packet_host"][2],
            "leading": max(0, row["target_x"] - row["packet_host"][0]),
            "reserve": max(0, row["target_x"] - row["packet_host"][0]),
            "screen_ready": True,
        },
    )


def rendered(header, host):
    return host + header.property("nativeHeaderInset")


def test_recorded_reveals_finish_with_native_allocation_without_catchup(child_header):  # noqa: F811
    _app, _bridge, main, header, _child, _boundary = child_header
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/mac_header_reveal_88c122e.json").read_text()
    )
    observations = []
    previous = None
    for sequence, row in enumerate(fixture["rows"], 1):
        if previous is not None:
            QTest.qWait(max(1, min(100, round((row["elapsed"] - previous) * 1000))))
        publish(main, row, sequence)
        host = row["packet_host"][0]
        if row["packet_content"][2] == 1440:
            # Genuine windowed exposed aperture96, fullscreen hidden10, target99.
            expected = max(host, 10 + min(1, max(0, (host - 10) / 86)) * 89)
            observations.append(
                (row["elapsed"], host, rendered(header, host), expected)
            )
        previous = row["elapsed"]
    # Fail specifically at arrival of each exposed native allocation, where
    # the captured predecessor remained96 then later caught up to99.
    arrivals = [r for r in observations if r[1] == 96]
    assert arrivals and all(abs(r[2] - 99) < 0.1 for r in arrivals), arrivals
    for _elapsed, _host, value, expected in observations:
        assert value == pytest.approx(expected, abs=0.1)
    # Hold the final native allocation: no second movement after its arrival.
    assert observations[-1][1:3] == pytest.approx((96, 99))
    for _ in range(25):
        QTest.qWait(10)
        assert rendered(header, 96) == pytest.approx(99)


def test_native_clock_conceal_and_reversal_are_geometry_driven(child_header):  # noqa: F811
    _app, _bridge, main, header, _child, _boundary = child_header
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/mac_header_reveal_88c122e.json").read_text()
    )
    initial = fixture["rows"][0]
    hidden = fixture["rows"][1]
    publish(main, initial, 1)
    publish(main, hidden, 2)
    sequence = 2
    for hosts in ([16, 40, 73, 96], [92, 63, 34], [44, 73, 96], [73, 34, 10]):
        values = []
        for host in hosts:
            sequence += 1
            row = dict(
                hidden,
                packet_host=[host, 822, 1432 - host, 44],
                target_x=99,
                packet_state="controls-visible",
            )
            publish(main, row, sequence)
            value = rendered(header, host)
            assert host <= value <= 99
            values.append(value)
            QTest.qWait(16)
        assert values == sorted(values, reverse=hosts[-1] < hosts[0])
    publish(main, hidden, sequence + 1)
    for _ in range(12):
        QTest.qWait(10)
        assert rendered(header, 10) == pytest.approx(10)


@pytest.mark.parametrize("origin", [-800, 300])
def test_native_clock_uses_relative_allocation_and_retains_boundary(
    child_header,  # noqa: F811
    origin,
):
    _app, _bridge, main, header, _child, _boundary = child_header
    rows = json.loads(
        (Path(__file__).parent / "fixtures/mac_header_reveal_88c122e.json").read_text()
    )["rows"]
    for sequence, original in enumerate([rows[0], rows[1]], 1):
        row = json.loads(json.dumps(original))
        row["packet_host"][0] += origin
        row["packet_content"][0] += origin
        row["target_x"] += origin
        publish(main, row, sequence)
    visible = dict(row, packet_state="controls-visible", target_x=origin + 99)
    for sequence, host in enumerate([40, 73, 96, 102, 96], 3):
        visible["packet_host"] = [origin + host, 822, 1432 - host, 44]
        publish(main, visible, sequence)
        expected = max(host, 10 + min(1, (host - 10) / 86) * 89)
        assert rendered(header, origin + host) == pytest.approx(origin + expected)
        QTest.qWait(16)
    # Reduced motion retains immediate target and the drawable clamp.
    main.setProperty("nativeHeaderReducedMotion", True)
    assert rendered(header, origin + 96) == pytest.approx(origin + 99)
    main.setProperty("nativeHeaderAttached", False)
    assert not header.property("nativeMotionMayAnimate")
    assert header.property("nativeExposedHostOffset") != header.property(
        "nativeExposedHostOffset"
    )
