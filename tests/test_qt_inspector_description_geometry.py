"""Description viewport fits beneath real selected-item recovery details."""

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
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
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
            root = capture_dir
            assert capture.save(str(root / "description-820x740-compact.png"))
            return
        window.findChild(QObject, "libraryFolderDescriptionTab").activated.emit()
        for _ in range(5):
            app.processEvents()
        scroll = window.findChild(QObject, "libraryFolderDescriptionScroll")
        controls = window.findChild(QObject, "libraryInspectorRecoveryDetails")
        root = capture_dir
        assert window.grabWindow().save(str(root / f"layout-{width}x{height}.png"))
        assert controls.isVisible()
        assert scroll.height() > 40
        bottom = scroll.mapToItem(window.contentItem(), QPointF(0, scroll.height())).y()
        assert bottom <= height - 20
        text = window.findChild(QObject, "libraryFolderDescriptionText")
        assert text.property("text") == record["description"]
        assert text.height() > scroll.height()
        capture = window.grabWindow()
        root = capture_dir
        capture.save(str(root / f"description-{width}x{height}.png"))
    finally:
        bridge.close()
        engine.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("mode", ["folders", "all"])
@pytest.mark.parametrize("width,height", [(1100, 740), (1100, 800), (2400, 740)])
def test_first_selected_description_tracks_live_table_geometry(
    tmp_path, monkeypatch, mode, width, height
):
    """Measure the table independently after navigation and a later resize."""
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtTest import QTest

    from tests.test_qt_scene_port import polish_scene

    for key in ("HOME", "LOCALAPPDATA", "XDG_DATA_HOME", "TMPDIR"):
        monkeypatch.setenv(key, str(tmp_path / key))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    output = tmp_path / "Downloads"
    folder = output / "Channel" / "videos - no playlist" / "Owned video"
    folder.mkdir(parents=True)
    path = folder / "media.mp4"
    path.write_bytes(b"Visual fixture; no decoding or export claim")
    record = saved(folder, "Long selected title with Unicode 日本語 🚀 " * 8, "MP4")
    record["vodforge_output_path"] = str(path)
    record["vodforge_retry_job"] = {"output_dir": str(output)}
    record["description"] = "First selected description remains readable. " * 40
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._timer.stop()
    bridge._runtime.history = [record]
    bridge.setOutputPath(str(output))
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]

    def settle_listing():
        for _ in range(300):
            QTest.qWait(10)
            bridge._pump()
            if not bridge._folder_listing_pending:
                assert not bridge._folder_listing_error
                return
        pytest.fail("Owned folder listing did not settle")

    def assert_visible_description():
        for _ in range(5):
            app.processEvents()
            polish_scene(window.contentItem())
        inspector = window.findChild(QObject, "libraryFolderInspector")
        table = window.findChild(QObject, "libraryFolderViewport")
        scroll = window.findChild(QObject, "libraryFolderDescriptionScroll")
        footer = window.findChild(QObject, "libraryInspectorActionFooter")
        expected = table.mapToItem(inspector, QPointF(0, table.height())).y()
        assert inspector.property("targetPanelBottom") == pytest.approx(expected, abs=1)
        assert scroll.isVisible() and scroll.height() >= 120
        assert footer.mapToItem(
            inspector, QPointF(0, footer.height())
        ).y() == pytest.approx(expected, abs=1)
        assert scroll.mapToItem(inspector, QPointF(0, scroll.height())).y() <= (
            footer.mapToItem(inspector, QPointF()).y() - inspector.property("spacing")
        )
        assert (
            window.findChild(QObject, "libraryFolderDescriptionText").property("text")
            == record["description"]
        )

    try:
        window.resize(width, height)
        QTest.qWait(20)
        bridge.select("Library")
        bridge.navigateLibraryFolders(mode)
        if mode == "folders":
            settle_listing()
            for _ in range(3):
                row = next(
                    row
                    for row in bridge.libraryFolders["components"]
                    if row["kind"] == "folder"
                )
                assert bridge.openLibraryFolderComponent(row["key"])
                settle_listing()
        row = next(
            row for row in bridge.libraryFolders["components"] if row["kind"] == "media"
        )
        assert bridge.selectLibraryFolderComponent(row["key"])
        app.processEvents()
        window.findChild(QObject, "libraryFolderDescriptionTab").activated.emit()
        assert_visible_description()
        window.resize(width + 100, height + 120)
        QTest.qWait(20)
        assert_visible_description()
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
        app.processEvents()
