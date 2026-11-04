import gc
import os
import sys
from pathlib import Path

import pytest


def pytest_configure():
    # Qt picks its display platform once, when the first test creates the
    # application. Scene tests ask for offscreen per test, but that only counts
    # if no earlier test created the app first, so results depended on test
    # order (on Windows, later tests ran in real desktop windows). Pin it for
    # the run; native opt-in runs choose their own platform.
    if os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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


@pytest.fixture(autouse=True)
def private_windows_user_folders(tmp_path_factory, monkeypatch):
    """Keep every test out of the real user's Windows profile.

    Tests isolate the app by setting HOME. On Windows the app's data folder
    follows LOCALAPPDATA and Path.home() follows USERPROFILE, so those tests
    read and wrote the real VODForge data of whoever ran them (on CI, one data
    folder shared by every test in the run). Point all three at a throwaway
    folder; a test that sets them itself still wins.
    """
    if sys.platform != "win32":
        yield
        return
    root = tmp_path_factory.mktemp("user-profile")
    monkeypatch.setenv("USERPROFILE", str(root))
    monkeypatch.setenv("LOCALAPPDATA", str(root / "AppData" / "Local"))
    monkeypatch.setenv("APPDATA", str(root / "AppData" / "Roaming"))
    yield


@pytest.fixture(autouse=True)
def no_leaked_child_process_observer():
    """A download sets a process-wide child-process observer and clears it when
    the run ends. A test that starts a run without finishing it would leave the
    observer behind, and a later test's fake processes would trip over it, so
    the outcome depended on test order. Clear it around every test."""
    from yt_downloader.download_service import set_active_child_process_observer

    set_active_child_process_observer(None)
    yield
    set_active_child_process_observer(None)


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
