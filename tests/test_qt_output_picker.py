"""Output picker source contracts; these do not prove native OS picker input."""

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject, QUrl
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app
from yt_downloader.qt_quick import main
from yt_downloader.settings_store import save_settings


@pytest.fixture
def picker_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qt_app()
    bridge = main.Bridge(None)
    yield bridge
    bridge.close()


def test_missing_downloads_picker_starts_at_home_not_nonexistent_destination(
    picker_bridge,
):
    bridge = picker_bridge
    assert not (Path.home() / "Downloads").exists()
    assert bridge.outputPath == str(Path.home() / "Downloads")
    assert bridge.outputFolderUrl.toLocalFile() == str(Path.home())


@pytest.mark.parametrize("name", ["Export folder", "日本語 café", "Literal %20 # name"])
def test_selected_local_folder_survives_immediate_close_and_restart(
    picker_bridge, tmp_path, name
):
    bridge = picker_bridge
    folder = tmp_path / name
    folder.mkdir()
    url = QUrl.fromLocalFile(str(folder))
    bridge.chooseOutputUrl(url)
    assert bridge.outputPath == str(folder)
    assert bridge.outputFolderUrl.toLocalFile() == str(folder)
    bridge.close()  # Flush pending debounce without waiting or changing cwd.
    restored = main.Bridge(None)
    try:
        assert restored.outputPath == str(folder)
        assert restored.outputFolderUrl == url
    finally:
        restored.close()


def test_removed_destination_picker_uses_existing_downloads_without_changing_save(
    picker_bridge, tmp_path
):
    bridge = picker_bridge
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    folder = tmp_path / "Removed output"
    folder.mkdir()
    bridge.chooseOutputUrl(QUrl.fromLocalFile(str(folder)))
    folder.rmdir()
    assert bridge.outputFolderUrl.toLocalFile() == str(downloads)
    assert bridge.outputPath == str(folder)


@pytest.mark.parametrize("name", ["missing", "regular-file"])
def test_invalid_selection_preserves_destination(picker_bridge, tmp_path, name):
    bridge = picker_bridge
    before = bridge.outputPath
    candidate = tmp_path / name
    if name == "regular-file":
        candidate.write_text("not a directory")
    bridge.chooseOutputUrl(QUrl.fromLocalFile(str(candidate)))
    assert bridge.outputPath == before
    assert bridge.status == "Select an existing output folder."


def test_nonlocal_url_cannot_be_output(picker_bridge):
    bridge = picker_bridge
    before = bridge.outputPath
    bridge.chooseOutputUrl(QUrl("https://example.invalid/folder"))
    assert bridge.outputPath == before


def test_saved_folder_survives_cwd_inside_bundle(picker_bridge, tmp_path, monkeypatch):
    bridge = picker_bridge
    folder = tmp_path / "Saved output"
    folder.mkdir()
    internals = tmp_path / "VODForge.app/Contents/MacOS"
    internals.mkdir(parents=True)
    monkeypatch.chdir(internals)
    bridge.chooseOutputUrl(QUrl.fromLocalFile(str(folder)))
    bridge.close()
    restored = main.Bridge(None)
    try:
        assert restored.outputFolderUrl.toLocalFile() == str(folder)
    finally:
        restored.close()


def test_unavailable_provider_falls_back_without_replacing_destination(
    picker_bridge, tmp_path, monkeypatch
):
    bridge = picker_bridge
    folder = tmp_path / "Unavailable provider"
    folder.mkdir()
    bridge.chooseOutputUrl(QUrl.fromLocalFile(str(folder)))
    original = Path.is_dir

    def failing(path):
        if path == folder:
            raise PermissionError("fixture provider unavailable")
        return original(path)

    monkeypatch.setattr(Path, "is_dir", failing)
    assert bridge.outputFolderUrl.toLocalFile() == str(tmp_path)
    assert bridge.outputPath == str(folder)


def test_relative_saved_destination_does_not_initialize_app_internal_cwd(
    picker_bridge, tmp_path, monkeypatch
):
    bridge = picker_bridge
    internals = tmp_path / "VODForge.app/Contents/MacOS"
    (internals / "relative-output").mkdir(parents=True)
    monkeypatch.chdir(internals)
    save_settings(bridge._settings_path, {"output_dir": "relative-output"})
    restored = main.Bridge(None)
    try:
        assert restored.outputFolderUrl.toLocalFile() == str(tmp_path)
    finally:
        restored.close()


def test_relative_selection_is_not_resolved_inside_package(
    picker_bridge, tmp_path, monkeypatch
):
    bridge = picker_bridge
    internals = tmp_path / "VODForge.app/Contents/MacOS"
    (internals / "relative-output").mkdir(parents=True)
    monkeypatch.chdir(internals)
    before = bridge.outputPath
    bridge.setOutputPath("relative-output")
    assert bridge.outputPath == before
    assert bridge.status == "Select an existing output folder."


def test_provider_failure_during_selection_is_reported_not_raised(
    picker_bridge, tmp_path, monkeypatch
):
    bridge = picker_bridge
    folder = tmp_path / "Unavailable provider"
    original = Path.is_dir

    def failing(path):
        if path == folder:
            raise PermissionError("fixture provider unavailable")
        return original(path)

    monkeypatch.setattr(Path, "is_dir", failing)
    before = bridge.outputPath
    bridge.chooseOutputUrl(QUrl.fromLocalFile(str(folder)))
    assert bridge.outputPath == before
    assert "unavailable" in bridge.status


def test_home_abbreviation_remains_supported(picker_bridge, tmp_path):
    folder = tmp_path / "Export with spaces"
    folder.mkdir()
    picker_bridge.setOutputPath("~/Export with spaces")
    assert picker_bridge.outputPath == str(folder)


def test_actual_qml_picker_reopens_at_changed_saved_destination(
    picker_bridge, tmp_path
):
    bridge = picker_bridge
    first = tmp_path / "First output"
    second = tmp_path / "Second output"
    first.mkdir()
    second.mkdir()
    bridge.chooseOutputUrl(QUrl.fromLocalFile(str(first)))
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    button = window.findChild(QObject, "forgeDestinationField")
    try:
        for folder in (first, second, second):
            bridge.chooseOutputUrl(QUrl.fromLocalFile(str(folder)))
            assert QMetaObject.invokeMethod(button, "activated")
            QTest.qWait(40)
            dialog = window.findChild(QObject, "outputFolderDialog")
            assert dialog.property("currentFolder").toLocalFile() == str(folder)
            assert QMetaObject.invokeMethod(dialog, "close")
            QTest.qWait(40)
            assert bridge.outputPath == str(folder)
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_repeated_trigger_does_not_replace_visible_picker(picker_bridge, tmp_path):
    bridge = picker_bridge
    folder = tmp_path / "Selected output"
    folder.mkdir()
    bridge.chooseOutputUrl(QUrl.fromLocalFile(str(folder)))
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    button = window.findChild(QObject, "forgeDestinationField")
    try:
        assert QMetaObject.invokeMethod(button, "activated")
        QTest.qWait(40)
        first = window.findChild(QObject, "outputFolderDialog")
        assert first.property("visible")
        assert QMetaObject.invokeMethod(button, "activated")
        QTest.qWait(40)
        assert window.findChild(QObject, "outputFolderDialog") is first
        assert bridge.outputPath == str(folder)
        assert QMetaObject.invokeMethod(first, "close")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
