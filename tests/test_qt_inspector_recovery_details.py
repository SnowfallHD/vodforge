"""Inspector recovery folder choice and selected metadata remain visible."""

from pathlib import Path

from PySide6.QtCore import QObject

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main as qt_main


def test_saved_inspector_always_has_metadata_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "Selected metadata", "MP4")]
    engine = qt_main.create_engine(bridge)
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("all")
        components = bridge.libraryFolders["components"]
        assert components
        assert bridge.selectLibraryFolderComponent(components[0]["key"])
        qt_app().processEvents()
        item = bridge.libraryFolderInspector
        assert item["source"] or item["output"]
        panel = engine.rootObjects()[0].findChild(QObject, "libraryFolderDetailsPanel")
        assert panel is not None
    finally:
        bridge.close()
        engine.deleteLater()
        qt_app().processEvents()


def test_retry_chooser_and_tooltips_use_exact_inspector_path():
    source = (Path(qt_main.__file__).parent / "LibraryFolderInspector.qml").read_text()
    assert (
        'issueFolderDialog.currentFolder = inspector.issueSettings.output_url || ""'
        in source
    )
    assert 'text: inspector.issueSettings.output_dir || ""' in source
    assert "visible: !inspector.recoveryActions.location && !!path" in source
    assert "selectedLocationHover" not in source
    assert (
        "(inspector.item.source || []).slice(0, 1).concat((inspector.item.output || []).slice(0, 1))"
        in source
    )
