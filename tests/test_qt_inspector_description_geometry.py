"""Description viewport fits beneath real selected-item recovery details."""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPointF

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main as qt_main


@pytest.mark.parametrize(
    "width,height", [(820, 740), (1100, 740), (1100, 900), (2400, 740)]
)
def test_description_viewport_fits_after_recovery_controls(
    tmp_path, monkeypatch, width, height
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    record = saved(
        tmp_path / ("long-folder-" * 12),
        "Selected media title with several words",
        "MP4",
    )
    record["description"] = "Long description retained and scrollable. " * 200
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(width, height)
        bridge.select("Library")
        bridge.navigateLibraryFolders("all")
        bridge.selectLibraryFolderComponent(
            bridge.libraryFolders["components"][0]["key"]
        )
        app.processEvents()
        if width == 820:
            window.findChild(QObject, "libraryFolderCompactDetails").activated.emit()
            app.processEvents()
            text = window.findChild(QObject, "libraryDescriptionText")
            assert text.property("text") == record["description"]
            viewport = window.findChild(QObject, "libraryDetailViewport")
            flickable = viewport.property("contentItem")
            flickable.setProperty(
                "contentY",
                min(
                    360,
                    max(
                        0,
                        flickable.property("contentHeight")
                        - flickable.property("height"),
                    ),
                ),
            )
            app.processEvents()
            capture = window.grabWindow()
            root = (
                Path(__file__).parents[2]
                / "integration-evidence/inspector-description-geometry"
            )
            assert capture.save(str(root / "description-820x740-compact.png"))
            return
        window.findChild(QObject, "libraryFolderDescriptionTab").activated.emit()
        for _ in range(5):
            app.processEvents()
        scroll = window.findChild(QObject, "libraryFolderDescriptionScroll")
        controls = window.findChild(QObject, "libraryInspectorRecoveryDetails")
        root = (
            Path(__file__).parents[2]
            / "integration-evidence/inspector-description-geometry"
        )
        assert window.grabWindow().save(str(root / f"layout-{width}x{height}.png"))
        assert controls.isVisible()
        assert scroll.height() > 40
        bottom = scroll.mapToItem(window.contentItem(), QPointF(0, scroll.height())).y()
        assert bottom <= height - 20
        text = window.findChild(QObject, "libraryFolderDescriptionText")
        assert text.property("text") == record["description"]
        assert text.height() > scroll.height()
        capture = window.grabWindow()
        root = (
            Path(__file__).parents[2]
            / "integration-evidence/inspector-description-geometry"
        )
        capture.save(str(root / f"description-{width}x{height}.png"))
    finally:
        bridge.close()
        engine.deleteLater()
        app.processEvents()
