"""Terminal ordering follows durable finish ordinals inside existing buckets."""

from dataclasses import replace

import pytest

from tests.test_qt_scene_port import qt_app, saved
from tests.test_run_identity import make_job
from yt_downloader.qt_quick.main import Bridge


@pytest.mark.parametrize(
    "status", ["Partial", "Failed", "Stopped", "Skipped", "Paused"]
)
@pytest.mark.parametrize("stamp", ["missing", "equal", "reversed_admission"])
def test_terminal_within_bucket_newest_first_without_reordering_other_owners(
    tmp_path, monkeypatch, status, stamp
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    runtime = bridge._runtime
    first = make_job(tmp_path)
    first.preview_info = {"title": "Same visible title"}
    newer = replace(
        first, run_id="newer-finished", preview_info={"title": "Same visible title"}
    )
    if stamp != "missing":
        # Preview/provider/admission dates are NOT terminal-completion times.
        first.preview_info["timestamp"] = 100 if stamp == "equal" else 200
        newer.preview_info["timestamp"] = 100
    runtime.recovery.terminal_attempt(first, status, "First retained issue")
    runtime.recovery.terminal_attempt(newer, status, "Newer retained issue")
    runtime.recovered = runtime.recovery.store.load_terminal_jobs()
    active = replace(first, run_id="active-owner")
    queue = [replace(first, run_id="queued-one"), replace(first, run_id="queued-two")]
    runtime.active_job = active
    runtime.queued = queue
    runtime.history = [
        saved(tmp_path, "Newer completed", "MP4"),
        saved(tmp_path, "Older completed", "MP4"),
    ]
    bridge._selected_run_key = "terminal:" + first.run_id
    monkeypatch.setattr(bridge._artwork, "request", lambda *_a, **_k: "")
    try:
        records = bridge.runDeck["records"]
        terminals = [r for r in records if r["kind"] == "terminal"]
        assert [r["runId"] for r in terminals] == [newer.run_id, first.run_id]
        assert [r["runId"] for r in records if r["kind"] == "queued"] == [
            q.run_id for q in queue
        ]
        assert [r["title"] for r in records if r["kind"] == "completed"] == [
            "Newer completed",
            "Older completed",
        ]
        assert records[0]["runId"] == active.run_id
        assert bridge.forgeSelection["runId"] == first.run_id
        assert (
            runtime.recovered[0].run_id == first.run_id
        )  # Do not mutate ledger ordering.
        kinds = [r["kind"] for r in records]
        if status == "Paused":
            assert kinds == [
                "active",
                "terminal",
                "terminal",
                "queued",
                "queued",
                "completed",
                "completed",
            ]
        else:
            assert kinds == [
                "active",
                "queued",
                "queued",
                "completed",
                "completed",
                "terminal",
                "terminal",
            ]
        # Existing recent-interruption promotion is a separate bucket rule.
        bridge._recent_interrupted_run_id = first.run_id
        promoted = bridge.runDeck["records"]
        if status != "Paused":
            assert [r["kind"] for r in promoted] == [
                "active",
                "queued",
                "queued",
                "terminal",
                "completed",
                "completed",
                "terminal",
            ]
            assert promoted[3]["runId"] == first.run_id
        assert bridge.forgeSelection["runId"] == first.run_id
        assert len(promoted) == 7  # No title merging, warning loss or deletion.
    finally:
        runtime.active_job = None
        runtime.queued = []
        bridge.close()


def test_rendered_run_deck_retains_interrupted_priority_and_newest_terminal_order(
    tmp_path, monkeypatch
):
    from PySide6.QtCore import QCoreApplication, QEvent, QObject

    from yt_downloader.qt_quick.main import create_engine

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = Bridge(None)
    first = make_job(tmp_path)
    first.terminal_status = "Partial"
    first.preview_info = {"title": "Same title"}
    newer = replace(first, run_id="newer-terminal")
    bridge._runtime.recovered = [first, newer]
    bridge._runtime.active_job = replace(first, run_id="active", terminal_status=None)
    bridge._runtime.queued = [replace(first, run_id="queued", terminal_status=None)]
    bridge._runtime.history = [saved(tmp_path, "Completed", "MP4")]
    monkeypatch.setattr(bridge._artwork, "request", lambda *_a, **_k: "")
    engine = create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        app.processEvents()
        deck = window.findChild(QObject, "forgeRunDeck")
        rows = deck.property("allRunsRecords").toVariant()
        assert [row["kind"] for row in rows] == [
            "active",
            "queued",
            "terminal",
            "terminal",
            "completed",
        ]
        assert [row["runId"] for row in rows[2:4]] == [newer.run_id, first.run_id]
        assert len(rows) == 5
    finally:
        bridge._runtime.active_job = None
        bridge._runtime.queued = []
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.mark.parametrize("count", [2, 3, 6])
def test_actual_qml_stably_preserves_both_groups_and_refreshes(
    tmp_path, monkeypatch, count
):
    from PySide6.QtCore import QCoreApplication, QEvent, QObject

    from yt_downloader.history import upsert_history
    from yt_downloader.qt_quick.main import create_engine

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = Bridge(None)
    source = make_job(tmp_path)
    statuses = ["Partial", "Stopped", "Skipped", "Failed"]
    history = []
    for index in range(count):
        job = replace(
            source,
            run_id=f"terminal-{index}",
            terminal_status=statuses[index % 4],
            preview_info={"title": "Same title"},
        )
        bridge._runtime.recovered.append(job)
        row = saved(tmp_path, f"owner-{index}", "MP4")
        row["title"] = "Same title"
        row["vodforge_run_id"] = job.run_id
        history = upsert_history(
            history, row, tmp_path, recorded_at=f"2026-10-18T13:00:{index:02d}+00:00"
        )
    bridge._runtime.history = history
    monkeypatch.setattr(bridge._artwork, "request", lambda *_a, **_k: "")
    engine = create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        deck = window.findChild(QObject, "forgeRunDeck")
        terminal_keys = [f"terminal:terminal-{i}" for i in reversed(range(count))]
        completed_keys = [
            r["selectionKey"]
            for r in bridge.runDeck["records"]
            if r["kind"] == "completed"
        ]
        assert bridge.selectRunRecord(completed_keys[-1])
        for refresh in range(3):
            if refresh:
                # A source metadata refresh changes a property, not completion
                # order. The correct shared history owner/order stays intact.
                bridge._runtime.history = [
                    {
                        **history[0],
                        "thumbnail": f"https://i.ytimg.com/vi/fixture/new-{refresh}.jpg",
                    },
                    *history[1:],
                ]
                bridge.runDeckChanged.emit()
            app.processEvents()
            rows = deck.property("allRunsRecords").toVariant()
            assert [r["selectionKey"] for r in rows] == terminal_keys + completed_keys
            assert [r["kind"] for r in rows] == ["terminal"] * count + [
                "completed"
            ] * count
            assert len(rows) == count * 2
            assert [r["vodforge_run_id"] for r in bridge._runtime.history] == [
                r["vodforge_run_id"] for r in history
            ]
            assert bridge.forgeSelection["selectionKey"] == completed_keys[-1]
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
