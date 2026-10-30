"""A QML-owned temporary popup trigger must not invalidate its main window."""

import gc
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
from shiboken6 import isValid

from tests.test_qt_header_native_clock import publish
from tests.test_qt_native_header_modal_boundary import (
    center,
    child_header,  # noqa: F401
    click,
    settle,
)


@pytest.mark.parametrize("press", ["outside", "inside", "foreign-window"])
def test_transient_trigger_wrapper(child_header, monkeypatch, press):  # noqa: F811
    app, bridge, main, header, child, _boundary = child_header
    monkeypatch.setattr(bridge, "isPointerPressed", lambda: True)
    context = QQmlEngine.contextForObject(header)
    find_trigger = """function find(i) { if(i.objectName === "forgeFormatButton") return i;
        for(let c of i.children) { let v = find(c); if(v) return v; } return null; }"""
    point_expression = QQmlExpression(
        context,
        main,
        "(function(){"
        + find_trigger
        + "const t=find(window.contentItem); return t.mapToItem(window.contentItem,t.width/2,t.height/2);})()",
    )
    point = point_expression.evaluate()[0]
    assert not point_expression.hasError()
    bridge._pointer_press = (
        child if press == "foreign-window" else main,
        QPointF(1, 1) if press == "outside" else point,
    )
    expr = QQmlExpression(
        context,
        main,
        """(function(){function find(i){if(i.objectName==="forgeFormatButton")return i;for(let c of i.children){let v=find(c);if(v)return v;}return null;}return bridge.isPointerPressOnItem(find(window.contentItem));})()""",
    )
    result = expr.evaluate()
    assert not expr.hasError(), expr.error().toString()
    assert result[0] is (press == "inside")
    gc.collect()
    app.processEvents()
    assert isValid(main), "main wrapper invalidated by transient trigger slot"
    assert isValid(header), "header wrapper invalidated"
    bridge._pointer_press = None


@pytest.mark.parametrize("open_delay", [1, 260])
@pytest.mark.parametrize("composer_focus", [False, True])
def test_format_composer_retreat_preserves_header(
    child_header,  # noqa: F811
    open_delay,
    composer_focus,
):
    app, bridge, main, header, child, boundary = child_header
    rows = json.loads(
        (
            Path(__file__).parent / "fixtures/mac_picker_retreat_20261023.json"
        ).read_text()
    )
    rows = [
        next(r for r in rows if t in r["utc"])
        for t in [
            "16:56:33.006926",
            "16:56:34.242304",
            "16:56:34.286726",
            "16:56:35.216047",
        ]
    ]
    popup = main.findChild(QObject, "forgeFormatPopup")
    for cycle in range(3):
        main.requestActivate()
        app.processEvents()
        publish(main, rows[0], cycle * 4 + 1)
        QTest.mouseClick(
            main, Qt.LeftButton, pos=center(main.contentItem(), "forgeFormatButton")
        )
        QTest.qWait(open_delay)
        assert popup.property("visible")
        assert not main.property("menuNavigationAllowed")
        QTest.mouseClick(
            main, Qt.LeftButton, pos=center(main.contentItem(), "forgeUrlInput")
        )
        # Popup dismissal may consume the click. Also cover an actual focus
        # transfer independently, without assuming it occurred on dismissal.
        composer = main.findChild(QObject, "forgeUrlInput")
        if composer_focus:
            composer.forceActiveFocus()
        for i, row in enumerate(rows[1:], 2):
            publish(main, row, cycle * 4 + i)
            app.processEvents()
            gc.collect()
            assert all(isValid(o) for o in (main, header, child, popup))
            assert header.parentItem() is child.contentItem()
            assert main.property("nativeHeaderAttached")
            assert header.isVisible() and header.opacity() == 1
        QTest.qWait(250)
        assert not popup.property("visible")
        if composer_focus:
            assert composer.property("activeFocus")
        assert main.property("menuNavigationAllowed")
        assert not popup.property("dismissedByTriggerPress")
        assert not boundary.owned
        assert bridge._pointer_press is None
        click(child, header, "navigationButton_Library")
        settle(app, header)
        assert bridge.selection == "Library"
        click(child, header, "navigationButton_Forge")
        settle(app, header)
        assert bridge.selection == "Forge"
