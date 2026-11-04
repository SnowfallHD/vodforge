"""Options panel "liquid" motion when Custom is chosen and then left.

Regression: at the common 1100pt window the four-column Custom layout missed by
4pt, so the Settings column restacked below the presets on the first frame
(jumping ~520pt), and on collapse the panel undershot its height and popped
back ~80ms after the animation ended. These checks sample real geometry while
the animation runs and assert its shape (no restack where it fits, monotonic
size, nothing moving after it ends), not frame timing.
"""

import itertools
import time

import pytest
from PySide6.QtCore import QMetaObject, QObject
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch


def _sample(app, menu, extras, ms=380):
    rows, start = [], time.perf_counter()
    while (time.perf_counter() - start) * 1000 < ms:
        app.processEvents()
        point = extras.mapToScene(extras.boundingRect().topLeft())
        rows.append(
            {
                "reveal": menu.property("customReveal"),
                "width": menu.property("width"),
                "height": menu.property("height"),
                "side": menu.property("sideBySideExtras"),
                "extras": (round(point.x(), 1), round(point.y(), 1)),
            }
        )
        QTest.qWait(8)
    return rows


def _run(tmp_path, monkeypatch, size):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    window.resize(*size)
    QTest.qWait(100)
    menu = window.findChild(QObject, "optionsMenu")
    extras = window.findChild(QQuickItem, "composerQuickExtras")
    QMetaObject.invokeMethod(menu, "open")
    QTest.qWait(400)
    start = (menu.property("width"), menu.property("height"))
    bridge.setExportMode("Manual Override")
    grow = _sample(app, menu, extras)
    everyday = next(
        o["value"] for o in bridge.exportModeOptions if o["label"] == "Everyday"
    )
    bridge.setExportMode(everyday)
    shrink = _sample(app, menu, extras)
    return (app, bridge, engine, window), start, grow, shrink


def _monotonic(values, rising):
    pairs = list(itertools.pairwise(values))
    return all((b >= a - 0.01) if rising else (b <= a + 0.01) for a, b in pairs)


@pytest.mark.parametrize("size", [(1100, 740), (1500, 900)])
def test_custom_reveal_keeps_columns_in_place_where_four_fit(
    tmp_path, monkeypatch, size
):
    scene, start, grow, shrink = _run(tmp_path, monkeypatch, size)
    try:
        assert all(row["side"] for row in grow + shrink), (
            "Settings column restacked mid-motion"
        )
        # Settings moves only by the panel's own resize: never a large step.
        # A step is judged against how far the animation advanced between the
        # two samples, so slow (software-rendered) runners that sample fewer
        # frames are held to the same rule as fast ones. The regression was a
        # ~520pt jump on the first frame, with almost no animation progress.
        for rows in (grow, shrink):
            travel = abs(rows[-1]["extras"][0] - rows[0]["extras"][0]) + abs(
                rows[-1]["extras"][1] - rows[0]["extras"][1]
            )
            for a, b in itertools.pairwise(rows):
                step = abs(b["extras"][0] - a["extras"][0]) + abs(
                    b["extras"][1] - a["extras"][1]
                )
                progress = abs(b["reveal"] - a["reveal"])
                assert step <= 40 + 2 * travel * progress, (step, progress, travel)
        for rows, rising in ((grow, True), (shrink, False)):
            assert _monotonic([r["width"] for r in rows], rising)
            assert _monotonic([r["height"] for r in rows], rising)
        assert grow[-1]["reveal"] == 1 and shrink[-1]["reveal"] == 0
        # Settled exactly where it started: no undershoot followed by a pop.
        assert (shrink[-1]["width"], shrink[-1]["height"]) == start
    finally:
        _close(scene[1], scene[2], scene[3])


def test_narrow_window_restacks_once_without_height_jumps(tmp_path, monkeypatch):
    scene, start, grow, shrink = _run(tmp_path, monkeypatch, (960, 700))
    try:
        # Restacking is decided by the target state: once, at the start.
        assert len({row["side"] for row in grow}) == 1 and not grow[0]["side"]
        assert len({row["side"] for row in shrink}) == 1 and shrink[0]["side"]
        assert _monotonic([r["height"] for r in grow], True), (
            "height dipped before growing"
        )
        assert _monotonic([r["width"] for r in grow], True)
        assert _monotonic([r["width"] for r in shrink], False)
        assert (shrink[-1]["width"], shrink[-1]["height"]) == start
    finally:
        _close(scene[1], scene[2], scene[3])
