"""Exercise exact-owner inspector recovery actions through the real Qt scene."""

from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtTest import QSignalSpy

from tests.test_qt_scene_port import qt_app, saved
from tests.test_run_identity import make_job
from yt_downloader.history import load_history, save_history
from yt_downloader.qt_quick import main as qt_main


@pytest.fixture
def scene(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    window.resize(1100, 800)
    try:
        yield app, bridge, window
    finally:
        window.close()
        app.processEvents()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def select_saved(bridge, root, names=("First", "Second")):
    bridge._runtime.history = [saved(root, name, "MP4") for name in names]
    for name in names:
        (root / f"{name}.mp4").write_bytes(b"fixture media, never trash")
    save_history(bridge._runtime.history_path, bridge._runtime.history)
    bridge.select("Library")
    bridge.navigateLibraryFolders("all")
    rows = [r for r in bridge.libraryFolders["components"] if r["kind"] == "media"]
    assert bridge.selectLibraryFolderComponent(rows[0]["key"])
    return rows


def button(root, label):
    return next(
        child
        for child in root.findChildren(QObject)
        if hasattr(child, "activated") and child.property("label") == label
    )


def test_saved_inspector_open_location_uses_selected_file_parent(
    scene, tmp_path, monkeypatch
):
    app, bridge, window = scene
    select_saved(bridge, tmp_path)
    app.processEvents()
    actions = bridge.inspectorRecoveryActions
    assert actions["location"] == bridge.libraryFolderInspector["location"]
    assert actions["canOpenLocation"]
    assert actions["savedOwner"] == bridge.libraryFolderInspector["owner"]
    assert not actions["dismissRunId"]
    opened = []
    monkeypatch.setattr(
        qt_main.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    window.findChild(QObject, "libraryInspectorOpenLocation").activated.emit()
    assert opened == [str(tmp_path)]


def test_saved_inspector_remove_requires_popup_and_keeps_files(scene, tmp_path):
    app, bridge, window = scene
    select_saved(bridge, tmp_path)
    app.processEvents()
    before = {p: p.read_bytes() for p in tmp_path.glob("*.mp4")}
    history = bridge._runtime.history_path.read_bytes()
    popup = window.findChild(QObject, "libraryRemovalConfirmation")
    window.findChild(QObject, "libraryInspectorRemoveCard").activated.emit()
    app.processEvents()
    assert popup.property("visible")
    assert bridge._runtime.history_path.read_bytes() == history
    text = [child.property("text") for child in popup.findChildren(QObject)]
    assert "The media file and folder stay on your computer." in text
    button(popup, "Cancel").activated.emit()
    app.processEvents()
    assert bridge._pending_library_removal is None
    assert bridge._runtime.history_path.read_bytes() == history
    window.findChild(QObject, "libraryInspectorRemoveCard").activated.emit()
    app.processEvents()
    button(popup, "Remove card").activated.emit()
    app.processEvents()
    assert len(bridge._runtime.history) == 1
    assert len(load_history(bridge._runtime.history_path)) == 1
    assert {p: p.read_bytes() for p in before} == before
    assert not popup.property("visible")


def test_stale_inspector_key_cannot_open_or_request_removal(
    scene, tmp_path, monkeypatch
):
    _, bridge, _ = scene
    rows = select_saved(bridge, tmp_path)
    old_key = bridge.inspectorRecoveryActions["selectionKey"]
    other = next(row for row in rows if row["key"] != old_key)
    assert bridge.selectLibraryFolderComponent(other["key"])
    opened = []
    monkeypatch.setattr(
        qt_main.QDesktopServices, "openUrl", lambda url: opened.append(url) or True
    )
    requested = QSignalSpy(bridge.libraryRemovalRequested)
    assert not bridge.openInspectorLocation(old_key)
    assert not bridge.requestInspectorLibraryRemoval(old_key)
    assert not opened
    assert requested.count() == 0
    assert bridge._pending_library_removal is None
    assert len(bridge._runtime.history) == 2


def test_unavailable_selected_location_does_not_launch_file_explorer(
    scene, tmp_path, monkeypatch
):
    _, bridge, _ = scene
    folder = tmp_path / "disposable-media"
    folder.mkdir()
    select_saved(bridge, folder, ("Missing fixture",))
    key = bridge.inspectorRecoveryActions["selectionKey"]
    (folder / "Missing fixture.mp4").unlink()
    folder.rmdir()
    opened = []
    monkeypatch.setattr(
        qt_main.QDesktopServices, "openUrl", lambda url: opened.append(url) or True
    )
    assert not bridge.inspectorRecoveryActions["canOpenLocation"]
    assert not bridge.openInspectorLocation(key)
    assert not opened
    assert len(bridge._runtime.history) == 1


def test_changed_record_rejects_pending_removal_confirmation(scene, tmp_path):
    _, bridge, _ = scene
    select_saved(bridge, tmp_path)
    key = bridge.inspectorRecoveryActions["selectionKey"]
    assert bridge.requestInspectorLibraryRemoval(key)
    owner = bridge.inspectorRecoveryActions["savedOwner"]
    record = bridge._saved_item_for_owner(owner)
    record["title"] = "Changed since confirmation"
    assert not bridge.confirmLibraryRemoval()
    assert len(bridge._runtime.history) == 2
    assert len(list(tmp_path.glob("*.mp4"))) == 2


@pytest.mark.parametrize("status", ["Failed", "Stopped", "Skipped"])
def test_issue_inspector_dismisses_terminal_only_and_keeps_saved_state(
    scene, tmp_path, monkeypatch, status
):
    app, bridge, window = scene
    media = tmp_path / "saved.mp4"
    media.write_bytes(b"retained media")
    bridge._runtime.history_path.parent.mkdir(parents=True, exist_ok=True)
    bridge._runtime.history_path.write_text('[{"id":"retained"}]')
    history = bridge._runtime.history_path.read_bytes()
    failed = make_job(tmp_path)
    failed.preview_info = {"title": "Interrupted fixture"}
    bridge._runtime.recovery.terminal_attempt(failed, status, "Fixture failure")
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    bridge.select("Library")
    bridge.navigateLibraryFolders("issues")
    issue = bridge.libraryFolders["components"][0]
    assert bridge.selectLibraryFolderComponent(issue["key"])
    app.processEvents()
    actions = bridge.inspectorRecoveryActions
    assert actions["dismissRunId"] == failed.run_id
    assert actions["location"] == str(tmp_path)
    assert not actions["savedOwner"]
    opened = []
    monkeypatch.setattr(
        qt_main.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    window.findChild(QObject, "libraryInspectorOpenLocation").activated.emit()
    assert opened == [str(tmp_path)]
    active = replace(make_job(tmp_path), run_id="active-fixture")
    queued = replace(make_job(tmp_path), run_id="queued-fixture")
    bridge._runtime.active_job = active
    bridge._runtime.queued = [queued]
    assert not bridge.dismissTerminal(active.run_id)
    assert not bridge.dismissTerminal(queued.run_id)
    window.findChild(QObject, "libraryInspectorDismissRun").activated.emit()
    app.processEvents()
    assert bridge._runtime.recovered == []
    assert bridge._runtime.recovery.store.load_terminal_jobs() == []
    assert bridge._runtime.active_job is active
    assert bridge._runtime.queued == [queued]
    assert not bridge.dismissTerminal(failed.run_id)
    assert media.read_bytes() == b"retained media"
    assert bridge._runtime.history_path.read_bytes() == history
    bridge._runtime.active_job = None
    bridge._runtime.queued = []


@pytest.mark.parametrize("width", [820, 1100])
def test_inspector_full_path_is_preserved_in_bounded_panel(scene, tmp_path, width):
    app, bridge, window = scene
    directory = tmp_path
    for i in range(12):
        directory /= f"long-readable-folder-{i}"
    directory.mkdir(parents=True)
    select_saved(bridge, directory, ("A long media title " * 6,))
    window.resize(width, 800)
    for _ in range(8):
        app.processEvents()
    inspector = window.findChild(QObject, "libraryFolderInspector")
    panel = window.findChild(QObject, "libraryInspectorRecoveryDetails")
    path = window.findChild(QObject, "libraryInspectorExactLocation")
    assert path.property("text") == bridge.inspectorRecoveryActions["location"]
    assert len(path.property("text")) > 300
    assert inspector.property("visible") == (width == 1100)
    assert inspector.width() <= window.width()
    if inspector.property("visible"):
        assert panel.width() == pytest.approx(inspector.width())
        assert 0 < panel.height() <= 168
        assert 0 < path.width() <= panel.width()
        assert path.property("lineCount") > 1
