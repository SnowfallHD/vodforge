"""Open endpoint requirements, not native reproductions or accepted fixes.

The current ABI does not distinguish the final native allocation from a reveal
passing through the same geometry. These desired-result regressions deliberately
remain failing on912b5ca until an authoritative endpoint can drive the layout.
Do not replace them with assertions of the incorrect position or timed waiting.
"""

import json
from pathlib import Path

from PySide6.QtTest import QTest

from tests.test_qt_header_native_clock import publish, rendered
from tests.test_qt_native_header_modal_boundary import child_header  # noqa: F401


def rows():
    return json.loads(
        (Path(__file__).parent / "fixtures/mac_header_reveal_88c122e.json").read_text()
    )["rows"]


def test_direct_fullscreen_has_no_late_clearance_catchup(child_header):  # noqa: F811
    _app, _bridge, main, header, _child, _boundary = child_header
    hidden = rows()[1]
    publish(main, hidden, 1)
    shown = dict(
        hidden,
        packet_host=[96, 822, 1336, 44],
        target_x=99,
        packet_state="controls-visible",
    )
    publish(main, shown, 2)
    at_arrival = rendered(header, 96)
    QTest.qWait(280)
    settled = rendered(header, 96)
    assert at_arrival == settled == 99, (at_arrival, settled)


def test_changed_native_endpoint_reaches_declared_clearance(child_header):  # noqa: F811
    _app, _bridge, main, header, _child, _boundary = child_header
    initial, hidden = rows()[:2]
    publish(main, initial, 1)
    publish(main, hidden, 2)
    shown = dict(
        hidden,
        packet_host=[80, 822, 1352, 44],
        target_x=99,
        packet_state="controls-visible",
    )
    publish(main, shown, 3)
    QTest.qWait(280)
    assert rendered(header, 80) == 99
