"""Qt relink handoff keeps the shared preview, verification and commit gates."""

from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl
from PySide6.QtGui import QGuiApplication

from yt_downloader.archive_paths import ArchivePath
from yt_downloader.history import (
    RETRY_JOB_METADATA_KEY,
    history_archive_owner,
    load_history,
    save_history,
)
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick.relink import QtRelinkSession
from yt_downloader.run_state import serialize_download_job


def _settle(session: QtRelinkSession) -> None:
    for _ in range(200):
        if session.poll():
            return
        time.sleep(0.01)
    raise AssertionError("Relink worker did not settle")


def test_qt_relink_requires_review_and_preserves_failed_or_stale_history(tmp_path):
    original = tmp_path / "old" / "movie.mp4"
    original.parent.mkdir()
    candidate = tmp_path / "new" / "movie.mp4"
    candidate.parent.mkdir()
    candidate.write_bytes(b"saved media fixture")
    history_path = tmp_path / "history.json"
    rows = [
        {
            "id": "movie",
            "title": "Movie",
            "vodforge_output_type": "MP4",
            "vodforge_output_dir": str(original.parent),
            "vodforge_output_path": str(original),
        }
    ]
    save_history(history_path, rows)
    rows = load_history(history_path)
    session = QtRelinkSession(history_path)
    try:
        from yt_downloader.history import history_archive_owner

        owner = history_archive_owner(rows[0])
        assert session.begin(owner, candidate, rows)
        assert not session.accept(rows)
        _settle(session)
        assert session.phase == "preview"
        assert session.eligible
        assert not session.accept([{**rows[0], "title": "Changed"}])
        assert session.phase == "stale"
        assert load_history(history_path)[0]["vodforge_output_path"] == str(original)

        assert session.begin(owner, candidate, rows)
        _settle(session)
        assert session.accept(rows)
        _settle(session)
        assert session.phase == "done"
        assert load_history(history_path)[0]["vodforge_output_path"] == str(candidate)
        assert session.updated_history[0]["vodforge_relinked"] is True
    finally:
        session.close()


def test_qt_relink_rejects_wrong_file_and_never_writes(tmp_path):
    original = tmp_path / "old" / "movie.mp4"
    original.parent.mkdir()
    candidate = tmp_path / "new" / "movie.mp3"
    candidate.parent.mkdir()
    candidate.write_bytes(b"other media")
    history_path = tmp_path / "history.json"
    rows = [
        {
            "id": "movie",
            "vodforge_output_type": "MP4",
            "vodforge_output_dir": str(original.parent),
            "vodforge_output_path": str(original),
        }
    ]
    save_history(history_path, rows)
    rows = load_history(history_path)
    session = QtRelinkSession(history_path)
    try:
        from yt_downloader.history import history_archive_owner

        assert session.begin(history_archive_owner(rows[0]), candidate, rows)
        _settle(session)
        assert session.phase == "error"
        assert not session.eligible
        assert not session.accept(rows)
        assert load_history(history_path)[0]["vodforge_output_path"] == str(original)
    finally:
        session.close()


def test_qt_relink_rejects_concurrent_disk_history_change(tmp_path):
    original = tmp_path / "old" / "movie.mp4"
    original.parent.mkdir()
    candidate = tmp_path / "new" / "movie.mp4"
    candidate.parent.mkdir()
    candidate.write_bytes(b"saved media")
    history_path = tmp_path / "history.json"
    save_history(
        history_path,
        [
            {
                "id": "movie",
                "title": "Before",
                "vodforge_output_type": "MP4",
                "vodforge_output_dir": str(original.parent),
                "vodforge_output_path": str(original),
            }
        ],
    )
    rows = load_history(history_path)
    session = QtRelinkSession(history_path)
    try:
        assert session.begin(history_archive_owner(rows[0]), candidate, rows)
        _settle(session)
        changed = [{**rows[0], "title": "Other writer"}]
        save_history(history_path, changed)
        assert session.accept(rows)
        _settle(session)
        assert session.phase == "error"
        assert load_history(history_path)[0]["title"] == "Other writer"
        assert load_history(history_path)[0]["vodforge_output_path"] == str(original)
    finally:
        session.close()


def test_qt_folder_relink_reviews_only_verified_files_and_keeps_other_history(tmp_path):
    source = tmp_path / "old"
    destination = tmp_path / "new"
    source.mkdir()
    destination.mkdir()
    (destination / "ready.mp4").write_bytes(b"ready media")
    rows = [
        {
            "id": name,
            "title": name,
            "vodforge_output_type": "MP4",
            "vodforge_output_dir": str(source),
            "vodforge_output_path": str(source / f"{name}.mp4"),
        }
        for name in ("ready", "missing")
    ]
    history_path = tmp_path / "history.json"
    save_history(history_path, rows)
    rows = load_history(history_path)
    session = QtRelinkSession(history_path)
    try:
        owners = tuple(history_archive_owner(row) for row in rows)
        assert session.begin_folder(
            ArchivePath.parse(str(source)),
            ArchivePath.parse(str(destination)),
            owners,
            rows,
        )
        _settle(session)
        assert session.phase == "preview"
        assert session.mode == "folder"
        assert session.selected == (0, 1)
        assert session.ready_indices == (0,)
        assert session.accept(rows)
        _settle(session)
        assert session.phase == "done"
        actual = load_history(history_path)
        assert actual[0]["vodforge_output_path"] == str(destination / "ready.mp4")
        assert actual[1]["vodforge_output_path"] == str(source / "missing.mp4")
    finally:
        session.close()


def test_qt_folder_relink_rejects_stale_scope_and_disk_history(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    source = tmp_path / "old"
    destination = tmp_path / "new"
    source.mkdir()
    destination.mkdir()
    (destination / "ready.mp4").write_bytes(b"ready media")
    rows = [
        {
            "id": "ready",
            "title": "Ready",
            "vodforge_output_type": "MP4",
            "vodforge_output_dir": str(source),
            "vodforge_output_path": str(source / "ready.mp4"),
        }
    ]
    save_history(bridge._runtime.history_path, rows)
    bridge._runtime.history = load_history(bridge._runtime.history_path)
    bridge.select("Library")
    bridge.navigateLibrary("folders")
    bridge.openLibraryFolderComponent(str(source.parent))
    bridge.openLibraryFolderComponent(str(source))
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    requested = []
    bridge.folderRelinkRequested.connect(requested.append)
    try:
        bridge.requestFolderRelink(str(source))
        assert requested == [str(source)]
        button = window.findChild(QObject, "libraryFolderRelinkButton")
        assert button is not None and button.property("visible")
        button.activated.emit()
        assert requested == [str(source), str(source)]
        assert not bridge.beginFolderRelink(
            str(source / "other"), QUrl.fromLocalFile(str(destination))
        )
        assert bridge.beginFolderRelink(
            str(source), QUrl.fromLocalFile(str(destination))
        )
        for _ in range(200):
            bridge._pump()
            if bridge.relinkInfo["phase"] == "preview":
                break
            time.sleep(0.01)
        assert bridge.relinkInfo["readyCount"] == 1
        save_history(bridge._runtime.history_path, [{**rows[0], "title": "Changed"}])
        assert bridge.acceptRelink()
        for _ in range(200):
            bridge._pump()
            if bridge.relinkInfo["phase"] == "error":
                break
            time.sleep(0.01)
        assert bridge.relinkInfo["phase"] == "error"
        assert load_history(bridge._runtime.history_path)[0]["title"] == "Changed"
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_missing_media_opens_review_and_serializes_history_writers(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    original = tmp_path / "old" / "movie.mp4"
    candidate = tmp_path / "new" / "movie.mp4"
    original.parent.mkdir()
    candidate.parent.mkdir()
    candidate.write_bytes(b"saved media fixture")
    rows = [
        {
            "id": "movie",
            "title": "Movie",
            "vodforge_output_type": "MP4",
            "vodforge_output_dir": str(original.parent),
            "vodforge_output_path": str(original),
        }
    ]
    save_history(bridge._runtime.history_path, rows)
    bridge._runtime.history = load_history(bridge._runtime.history_path)
    owner = history_archive_owner(bridge._runtime.history[0])
    requested = []
    bridge.missingMediaRequested.connect(lambda: requested.append(True))
    try:
        assert not bridge.openLibraryItem(0)
        assert requested == [True]
        assert bridge.missingMedia["owner"] == owner
        app.processEvents()
        assert (
            engine.rootObjects()[0]
            .findChild(QObject, "missingMediaPopup")
            .property("visible")
        )
        assert bridge.openLibraryDetails(owner)
        assert bridge.beginRelink(owner, QUrl.fromLocalFile(str(candidate)))
        for _ in range(200):
            bridge._pump()
            app.processEvents()
            if bridge.relinkInfo["phase"] == "preview":
                break
            time.sleep(0.01)
        assert bridge.relinkInfo["eligible"]
        assert not bridge.importMedia([QUrl.fromLocalFile(str(candidate))])
        assert not bridge.prepareLibraryRemoval(owner)
        assert bridge.acceptRelink()
        for _ in range(200):
            bridge._pump()
            app.processEvents()
            if bridge.relinkInfo["phase"] == "done":
                break
            time.sleep(0.01)
        assert bridge.relinkInfo["phase"] == "done"
        assert bridge._runtime.history[0]["vodforge_output_path"] == str(candidate)
        assert bridge.libraryDetail["owner"] == history_archive_owner(
            bridge._runtime.history[0]
        )
    finally:
        engine.rootObjects()[0].close()
        bridge.close()


def test_qt_missing_media_can_prepare_forge_without_changing_default(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    output_default = bridge._output_path
    old = tmp_path / "archive" / "missing.mp4"
    old.parent.mkdir()
    rows = [
        {
            "id": "abcdefghijk",
            "title": "Missing",
            "vodforge_output_type": "MP4",
            "vodforge_output_dir": str(old.parent),
            "vodforge_output_path": str(old),
        }
    ]
    save_history(bridge._runtime.history_path, rows)
    bridge._runtime.history = load_history(bridge._runtime.history_path)
    prepared = []
    bridge.sourcePrepared.connect(prepared.append)
    try:
        assert not bridge.openLibraryItem(0)
        assert bridge.missingMedia["primaryAction"] == "open_forge"
        assert bridge.openMissingInForge(QUrl.fromLocalFile(str(tmp_path)))
        assert prepared == ["https://www.youtube.com/watch?v=abcdefghijk"]
        assert bridge.outputPath == str(tmp_path)
        assert bridge._output_path == output_default
    finally:
        bridge.close()


def test_qt_missing_media_redownload_uses_saved_job_and_retires_only_its_card(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    root = tmp_path / "downloads"
    root.mkdir()
    missing = root / "channel" / "missing.mp4"
    missing.parent.mkdir()
    job = bridge._runtime.prepare_job(
        "https://www.youtube.com/watch?v=abcdefghijk", root, "MP4", "Everyday"
    )
    rows = [
        {
            "id": "abcdefghijk",
            "title": "Missing",
            "vodforge_output_type": "MP4",
            "vodforge_output_dir": str(missing.parent),
            "vodforge_output_path": str(missing),
            RETRY_JOB_METADATA_KEY: serialize_download_job(job),
        }
    ]
    save_history(bridge._runtime.history_path, rows)
    bridge._runtime.history = load_history(bridge._runtime.history_path)
    admitted = []
    monkeypatch.setattr(
        bridge._runtime,
        "start_job",
        lambda recovered: admitted.append(recovered) or recovered,
    )
    try:
        assert not bridge.openLibraryItem(0)
        assert bridge.missingMedia["primaryAction"] == "redownload"
        assert bridge.redownloadMissingTo()
        assert len(admitted) == 1
        assert admitted[0].recovery_reason == "missing_media"
        assert admitted[0].urls == ["https://www.youtube.com/watch?v=abcdefghijk"]
        assert bridge._runtime.history == []
        assert load_history(bridge._runtime.history_path) == []
    finally:
        bridge.close()
