"""Recovering resources retain actual metadata and controls in the existing deck."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from tests.test_qt_scene_port import qt_app
from tests.test_recovery_isolation import interrupted
from yt_downloader.qt_quick.main import Bridge, create_engine


@pytest.mark.parametrize("metadata", [True, False])
def test_actual_deck_recovery_metadata_cancel_and_explicit_retry(
    tmp_path, monkeypatch, metadata
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = Bridge(None)
    runtime = bridge._runtime
    store, job, stage = interrupted(tmp_path)
    if not metadata:
        store.update_preview(job.run_id, {})
        # Empty legacy preview is a valid incomplete record, not fabricated metadata.
        payload = store.load()
        payload["job"]["preview_info"] = {}
        store._write_unlocked(payload)
    runtime.recovery.store = store
    store.prepare_recovery()
    runtime.recovered = store.load_terminal_jobs()
    runtime._refresh_resource_recoveries()
    art = []
    monkeypatch.setattr(
        bridge._artwork, "request", lambda info, **kw: art.append(dict(info)) or ""
    )
    engine = create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        record = next(r for r in bridge.runDeck["records"] if r["runId"] == job.run_id)
        assert record["status"] == "Waiting for recovery"
        assert record["protectedRecovery"] and record["recoveryPending"]
        assert not record["retryEnabled"]
        assert record["title"] == (
            "Recover this video"
            if metadata
            else "Interrupted download (metadata not saved)"
        )
        if metadata:
            assert record["detail"] == "Creator · Collection"
            assert any(
                row.get("thumbnail") == "https://example.test/thumb.jpg" for row in art
            )
        deck = window.findChild(QObject, "forgeRunDeck")
        deck.setProperty("selectedRecord", record)
        popup = window.findChild(QObject, "runActionsPopup")
        popup.open()
        app.processEvents()
        cancel = window.findChild(QObject, "cancelResourceRecovery")
        assert cancel.property("visible")
        assert cancel.property("label") == "Cancel recovery"
        assert bridge.cancelResourceRecovery(job.run_id)
        assert (stage / "video.part").read_bytes() == b"private partial"
        after = next(r for r in bridge.runDeck["records"] if r["runId"] == job.run_id)
        assert after["status"] == "Stopped" and not after["recoveryPending"]
        assert after["retryLabel"] == "Retry recovery" and after["retryEnabled"]
        assert runtime.recovered[0].run_id == job.run_id
        # Cancellation is durable across a fresh journal reader; no retry on startup.
        from yt_downloader.run_state import ActiveRunStore

        reopened = ActiveRunStore(store.path)
        reopened.prepare_recovery()
        assert not reopened.pending_recovery_jobs()
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
