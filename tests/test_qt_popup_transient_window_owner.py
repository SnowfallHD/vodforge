"""A QML-owned temporary popup trigger must not invalidate its main window."""

import gc

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtQml import QQmlEngine, QQmlExpression
from shiboken6 import isValid

from tests.test_qt_native_header_modal_boundary import child_header  # noqa: F401


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
