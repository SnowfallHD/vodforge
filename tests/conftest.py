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


@pytest.fixture
def production_telemetry_contract(monkeypatch):
    """Exercise release logic with the individual tests' fake transports only."""
    from yt_downloader import (
        analytics_consent,
        cloud_funnel,
        heycatch_telemetry,
        install_attribution,
        product_telemetry,
    )

    for module in (
        analytics_consent,
        cloud_funnel,
        heycatch_telemetry,
        install_attribution,
        product_telemetry,
    ):
        name = (
            "production_telemetry_allowed"
            if module is heycatch_telemetry
            else "telemetry_collection_allowed"
        )
        monkeypatch.setattr(module, name, lambda: True)
