"""Header tooltip must keep the real main window as its transient owner."""

from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlContext, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

from tests.test_qt_native_header_modal_boundary import child_header  # noqa: F401


def test_header_tooltip_uses_main_transient_owner(child_header, capfd):  # noqa: F811
    app, _bridge, main, header, child, _boundary = child_header
    button = header.findChild(QObject, "headerXButton")
    tooltip = next(
        obj
        for obj in button.children()
        if obj.metaObject().indexOfProperty("independentWindow") >= 0
    )
    tooltip.setProperty("visible", True)
    try:
        QTest.qWait(300)
        app.processEvents()
        popups = [
            w
            for w in QGuiApplication.topLevelWindows()
            if w not in (main, child) and w.isVisible()
        ]
        assert len(popups) == 1
        context = QQmlContext(QQmlEngine.contextForObject(header))
        context.setContextProperty("expectedMainWindow", main)
        result = QQmlExpression(
            context, tooltip, "parent === expectedMainWindow.contentItem"
        ).evaluate()
        assert result[0] is True
        assert "must be a top level window" not in capfd.readouterr().err
    finally:
        tooltip.setProperty("visible", False)
        QTest.qWait(220)
