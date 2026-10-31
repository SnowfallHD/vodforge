import gc
import os
import sys
from pathlib import Path

import pytest


def pytest_configure():
    # Windows offscreen Qt does not discover the native font directory itself.
    # Use installed fonts so geometry checks measure Segoe UI, not fallback boxes.
    if sys.platform == "win32":
        fonts = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts"
        if fonts.is_dir():
            os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))


@pytest.fixture(autouse=True)
def qt_gui_thread_collection(request):
    """Collect cyclic Qt wrappers on the test thread, never an archive worker.

    CPython can trigger collection in any allocating thread. Scene tests leave
    signal/owner cycles that PySide must dispose on the GUI thread; collecting
    them while the next test's worker starts can crash the native Qt runtime.
    Product cleanup and all assertions remain exercised normally.
    """
    if not request.node.path.name.startswith("test_qt_"):
        yield
        return
    enabled = gc.isenabled()
    gc.disable()
    gc.collect()
    try:
        yield
    finally:
        gc.collect()
        if enabled:
            gc.enable()


@pytest.fixture(autouse=True)
def offscreen_cursor_starts_outside_windows():
    """Tests that move the real offscreen cursor must not leak it.

    Hover admission reads QCursor.pos(), which is process-wide. A cursor left
    over a trigger by one test opens that popup in the next. Only the offscreen
    platform is touched, so a native run never moves the user's pointer.
    """
    try:
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QCursor, QGuiApplication
    except ImportError:
        yield
        return
    app = QGuiApplication.instance()
    if app is not None and QGuiApplication.platformName() == "offscreen":
        QCursor.setPos(QPoint(-500, -500))
    yield


@pytest.fixture
def production_telemetry_contract(monkeypatch):
    """Exercise release logic with the individual tests' fake transports only."""
    from yt_downloader import (
        analytics_consent,
        cloud_funnel,
        install_attribution,
        product_telemetry,
    )

    for module in (
        analytics_consent,
        cloud_funnel,
        install_attribution,
        product_telemetry,
    ):
        monkeypatch.setattr(module, "telemetry_collection_allowed", lambda: True)
