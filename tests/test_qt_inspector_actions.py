"""Exercise exact-owner inspector recovery actions through the real Qt scene."""

from dataclasses import replace
from pathlib import Path

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
    bridge._timer.stop()
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    window.resize(1100, 800)
    app.processEvents()  # Complete deferred startup before seeding test owners.
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
    assert [Path(location) for location in opened] == [tmp_path]


def test_saved_inspector_remove_reviews_and_trashes_only_selected_file(
    scene, tmp_path, monkeypatch
):
    from yt_downloader import archive_file_operations as ops
    from yt_downloader.qt_quick import library_files

    app, bridge, window = scene
    rows = []
    for name in ("First", "Second"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / f"{name}.mp4").write_bytes(b"fixture media")
        rows.append(saved(folder, name, "MP4"))
    bridge._runtime.history = rows
    save_history(bridge._runtime.history_path, rows)
    bridge._runtime.history = load_history(bridge._runtime.history_path)
    bridge.select("Library")
    bridge.navigateLibraryFolders("all")
    row = next(r for r in bridge.libraryFolders["components"] if r["kind"] == "media")
    assert bridge.selectLibraryFolderComponent(row["key"])
    owner = bridge.inspectorRecoveryActions["savedOwner"]
    selected = Path(bridge._saved_item_for_owner(owner)["vodforge_output_path"])
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.mp4")}
    history = bridge._runtime.history_path.read_bytes()
    trash = tmp_path / "synthetic-trash"
    trash.mkdir()

    def fake_trash(path):
        target = trash / path.name
        path.rename(target)
        return str(target)

    monkeypatch.setattr(library_files, "system_trash_available", lambda: True)
    monkeypatch.setattr(
        library_files,
        "delete_files",
        lambda *a, **k: ops.delete_files(*a, **k, trash=fake_trash),
    )
    popup = window.findChild(QObject, "libraryFileActionPopup")
    for confirm in (False, True):
        window.findChild(QObject, "libraryInspectorRemoveCard").activated.emit()
        bridge._files.worker.join(timeout=10)
        bridge._pump()
        app.processEvents()
        assert popup.property("visible")
        assert bridge.fileActionEligible, bridge.fileActionStatus
        assert bridge._runtime.history_path.read_bytes() == history
        assert {p: p.read_bytes() for p in before} == before
        if not confirm:
            popup.findChild(QObject, "fileActionDismissButton").activated.emit()
            app.processEvents()
            assert not popup.property("visible")
        else:
            assert bridge.confirmFileAction()
            bridge._files.worker.join(timeout=10)
            bridge._pump()
    assert bridge._files.phase == "done", bridge.fileActionStatus
    assert len(load_history(bridge._runtime.history_path)) == 1
    assert not selected.exists()
    assert (trash / selected.name).read_bytes() == before[selected]
    assert all(p.read_bytes() == data for p, data in before.items() if p != selected)


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
    requested = QSignalSpy(bridge.fileActionRequested)
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
    # This test removes its fixture to simulate an external disappearance;
    # prevent asynchronous artwork reads from racing that Windows unlink.
    bridge._artwork.close()
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


def test_changed_record_rejects_pending_removal_confirmation(
    scene, tmp_path, monkeypatch
):
    from yt_downloader.qt_quick import library_files

    _, bridge, _ = scene
    select_saved(bridge, tmp_path, ("First",))
    bridge._runtime.history = load_history(bridge._runtime.history_path)
    monkeypatch.setattr(library_files, "system_trash_available", lambda: True)
    key = bridge.inspectorRecoveryActions["selectionKey"]
    assert bridge.requestInspectorLibraryRemoval(key)
    bridge._files.worker.join(timeout=10)
    bridge._pump()
    assert bridge.fileActionEligible
    owner = bridge.inspectorRecoveryActions["savedOwner"]
    record = bridge._saved_item_for_owner(owner)
    record["title"] = "Changed since confirmation"
    assert not bridge.confirmFileAction()
    assert len(bridge._runtime.history) == 1
    assert len(list(tmp_path.glob("*.mp4"))) == 1


@pytest.mark.parametrize(
    "status", ["Failed", "Stopped", "Skipped", "Paused", "Partial"]
)
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
    assert [Path(location) for location in opened] == [tmp_path]
    active = replace(make_job(tmp_path), run_id="active-fixture")
    queued = replace(make_job(tmp_path), run_id="queued-fixture")
    bridge._runtime.active_job = active
    bridge._runtime.queued = [queued]
    assert not bridge.dismissTerminal(active.run_id)
    assert not bridge.dismissTerminal(queued.run_id)
    window.findChild(QObject, "libraryInspectorDismissRun").activated.emit()
    app.processEvents()
    assert len(bridge._runtime.recovered) == 1
    assert bridge._runtime.active_job is active
    assert bridge._runtime.queued == [queued]
    bridge._runtime.active_job = None
    bridge._runtime.queued = []
    window.findChild(QObject, "libraryInspectorDismissRun").activated.emit()
    app.processEvents()
    assert window.findChild(QObject, "libraryFileActionPopup").property("visible")
    assert len(bridge._runtime.recovered) == 1
    assert bridge.confirmFileAction()
    assert bridge._runtime.recovered == []
    assert bridge._runtime.recovery.store.load_terminal_jobs() == []
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
    assert path.property("path") == bridge.inspectorRecoveryActions["location"]
    assert len(path.property("path")) > 300
    assert inspector.property("visible") == (width == 1100)
    assert inspector.width() <= window.width()
    if inspector.property("visible"):
        assert panel.width() == pytest.approx(inspector.width())
        assert 0 < panel.height() <= 168
        assert 0 < path.width() <= panel.width()
        assert path.height() == 34
        label = path.findChild(QObject, "outputPathText")
        assert label.property("lineCount") == 1


@pytest.mark.parametrize("failure", [PermissionError("denied"), OSError("offline")])
@pytest.mark.parametrize("owner_kind", ["saved", "failed"])
def test_denied_location_preserves_exact_owner_recovery_actions(
    scene, tmp_path, monkeypatch, failure, owner_kind
):
    app, bridge, window = scene
    folder = tmp_path / "denied-media-folder"
    folder.mkdir()
    media = folder / "retained.mp4"
    media.write_bytes(b"retained fixture media")
    if owner_kind == "saved":
        select_saved(bridge, folder, ("retained",))
    else:
        job = make_job(folder)
        bridge._runtime.recovery.terminal_attempt(job, "Failed", "Fixture failure")
        bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        issue = bridge.libraryFolders["components"][0]
        assert bridge.selectLibraryFolderComponent(issue["key"])
    app.processEvents()
    original_actions = bridge.inspectorRecoveryActions
    original_media = media.read_bytes()
    history = (
        bridge._runtime.history_path.read_bytes()
        if bridge._runtime.history_path.exists()
        else None
    )
    is_dir = Path.is_dir

    def denied_probe(path):
        if path == folder:
            raise failure
        return is_dir(path)

    monkeypatch.setattr(Path, "is_dir", denied_probe)
    opened = []
    monkeypatch.setattr(
        qt_main.QDesktopServices, "openUrl", lambda url: opened.append(url) or True
    )
    actions = bridge.inspectorRecoveryActions
    assert not actions["canOpenLocation"]
    for key in ("selectionKey", "location", "savedOwner", "dismissRunId"):
        assert actions[key] == original_actions[key]
    assert not bridge.openInspectorLocation(actions["selectionKey"])
    assert not opened
    bridge.historyChanged.emit()
    app.processEvents()
    assert not window.findChild(QObject, "libraryInspectorOpenLocation").property(
        "visible"
    )
    if owner_kind == "saved":
        control = window.findChild(QObject, "libraryInspectorRemoveCard")
        assert control.property("visible")
        requested = QSignalSpy(bridge.fileActionRequested)
        control.activated.emit()
        assert requested.count() == 1
        assert bridge._files.action == "delete"
        bridge._files.worker.join(timeout=10)
        bridge._pump()
    else:
        control = window.findChild(QObject, "libraryInspectorDismissRun")
        assert control.property("visible")
        control.activated.emit()
        assert len(bridge._runtime.recovered) == 1
        assert len(bridge._runtime.recovery.store.load_terminal_jobs()) == 1
        bridge.cancelRunRemovalReview()
        assert bridge._remove_run_request is None
    assert media.read_bytes() == original_media
    if history is not None:
        assert bridge._runtime.history_path.read_bytes() == history
