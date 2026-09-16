from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.test_archive_relink import mapping, record
from tests.test_archive_ui_owners import Variable
from yt_downloader import history
from yt_downloader.archive_relink import (
    preview_relink,
    relocated_records,
    verify_relink,
)


def stage(path, item):
    history.stage_history_mutation(path, {"kind": "record", "record": item})


def test_pending_records_coalesce_by_exact_identity_and_replay_without_media_probes(
    tmp_path, monkeypatch
):
    ledger = tmp_path / "history.json"
    first = record(tmp_path / "first.mp4", identity="first")
    next_item = record(tmp_path / "next.mp4", identity="next")
    history.save_history(ledger, [first])
    stage(ledger, next_item)
    stage(ledger, {**next_item, "title": "Latest accepted title"})
    assert (
        len(json.loads(history.pending_history_path(ledger).read_text())["operations"])
        == 1
    )
    monkeypatch.setattr(
        history,
        "history_media_file_state",
        lambda *args: pytest.fail("Replay probed media"),
    )
    observed = []
    restored = history.load_history(ledger, on_recovered=observed.append)
    assert observed == [1] and len(restored) == 2
    assert restored[0]["title"] == "Latest accepted title"
    assert restored[1]["id"] == "first"
    assert not history.pending_history_path(ledger).exists()
    assert history.load_history(ledger) == restored
    assert not (tmp_path / "next.mp4").exists()


@pytest.mark.parametrize("failure", ["save", "retire"])
def test_interrupted_replay_retains_journal_and_retries_idempotently(
    tmp_path, monkeypatch, failure
):
    ledger = tmp_path / "history.json"
    original = record(tmp_path / "first.mp4", identity="first")
    pending = record(tmp_path / "second.mp4", identity="second")
    history.save_history(ledger, [original])
    stage(ledger, pending)
    before = ledger.read_bytes()
    journal_before = history.pending_history_path(ledger).read_bytes()
    with monkeypatch.context() as injected:
        if failure == "save":

            def fail(*args):
                raise history.HistoryError("Injected durable save failure")

            injected.setattr(history, "save_history", fail)
        else:
            original_unlink = history.Path.unlink

            def fail_retire(path, *args, **kwargs):
                if path == history.pending_history_path(ledger):
                    raise PermissionError("Injected post-save interruption")
                return original_unlink(path, *args, **kwargs)

            injected.setattr(history.Path, "unlink", fail_retire)
        with pytest.raises(history.HistoryError):
            history.load_history(ledger)
    assert history.pending_history_path(ledger).read_bytes() == journal_before
    if failure == "save":
        assert ledger.read_bytes() == before
    restored = history.load_history(ledger)
    assert {item["id"] for item in restored} == {"first", "second"}
    assert len(restored) == 2
    assert history.load_history(ledger) == restored


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "[]",
        '{"schema_version":2,"operations":[]}',
        '{"schema_version":1,"operations":[{"kind":"unknown"}]}',
    ],
)
def test_invalid_pending_data_never_overwrites_history_or_recovery_file(
    tmp_path, payload
):
    ledger = tmp_path / "history.json"
    history.save_history(ledger, [record(tmp_path / "first.mp4")])
    journal = history.pending_history_path(ledger)
    journal.write_text(payload)
    before = ledger.read_bytes()
    with pytest.raises(history.HistoryError):
        history.load_history(ledger)
    assert ledger.read_bytes() == before and journal.read_text() == payload


def test_pending_read_failure_and_limit_rejection_preserve_accepted_updates(
    tmp_path, monkeypatch
):
    ledger = tmp_path / "history.json"
    monkeypatch.setattr(history, "MAX_HISTORY_ITEMS", 2)
    stage(ledger, record(tmp_path / "a.mp4", identity="a"))
    stage(ledger, record(tmp_path / "b.mp4", identity="b"))
    journal = history.pending_history_path(ledger)
    accepted = journal.read_bytes()
    with pytest.raises(history.HistoryError):
        stage(ledger, record(tmp_path / "c.mp4", identity="c"))
    assert journal.read_bytes() == accepted
    original_read = history.Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == journal:
            raise PermissionError("Injected read failure")
        return original_read(path, *args, **kwargs)

    with monkeypatch.context() as injected:
        injected.setattr(history.Path, "read_text", unreadable)
        with pytest.raises(history.HistoryError):
            history.load_history(ledger)
    assert journal.read_bytes() == accepted


def test_pending_activity_follows_relinked_identity_and_future_saved_run(tmp_path):
    ledger = tmp_path / "history.json"
    destination = tmp_path / "new"
    destination.mkdir()
    (destination / "clip.mp4").write_bytes(b"synthetic")
    original = record(tmp_path / "old" / "clip.mp4", run="run-one")
    rows = [original]
    checked = verify_relink(
        preview_relink(rows, [mapping(tmp_path / "old", destination)]), rows
    )
    moved = relocated_records(checked, rows, accepted=[0])
    history.save_history(ledger, moved)
    future = record(tmp_path / "future.mp4", identity="future", run="run-one")
    stage(ledger, future)
    history.stage_history_mutation(
        ledger,
        {
            "kind": "activity",
            "owners": [history.history_archive_owner(original)],
            "run_id": "run-one",
            "activity": ["Final activity"],
        },
    )
    restored = history.load_history(ledger)
    assert all(item["vodforge_run_activity"] == ["Final activity"] for item in restored)
    relocated = next(item for item in restored if item["id"] == "video")
    assert relocated["vodforge_output_path"] == str(destination / "clip.mp4")


def test_failed_startup_recovery_blocks_destructive_empty_history_fallback(tmp_path):
    from yt_downloader.app import DownloaderApp

    ledger = tmp_path / "history.json"
    history.save_history(ledger, [record(tmp_path / "original.mp4")])
    history.pending_history_path(ledger).write_text("{invalid")
    before = ledger.read_bytes()
    app = SimpleNamespace(
        history_path=ledger, _append_log=lambda *args: None, status_var=Variable()
    )
    DownloaderApp._load_download_history(app)
    assert app._history_recovery_blocked
    DownloaderApp._record_download_history(app, record(tmp_path / "new.mp4"), tmp_path)
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("kind", ["record", "activity"])
def test_settled_callbacks_cannot_be_overwritten_by_earlier_journal_snapshot(
    tmp_path, kind
):
    from types import MethodType

    from yt_downloader.archive_library_ui import ArchiveLibraryMixin

    ledger = tmp_path / "history.json"
    item = record(tmp_path / "clip.mp4")
    history.save_history(ledger, [item])
    app = SimpleNamespace(
        history_path=ledger,
        download_history=[item],
        status_var=Variable(),
        _archive_usage=lambda *a, **k: None,
        _event_write_diagnostic=lambda *a: None,
    )
    app._archive_defer_history = MethodType(
        ArchiveLibraryMixin._archive_defer_history, app
    )
    early = {
        **item,
        "title": "Initially accepted",
        "vodforge_run_activity": ["Accepted"],
    }
    mutation = (
        {"kind": "record", "record": early}
        if kind == "record"
        else {
            "kind": "activity",
            "owners": [history.history_archive_owner(item)],
            "activity": ["Accepted"],
        }
    )

    def latest_callback():
        app.download_history[0] = {
            **app.download_history[0],
            "title": "Settled title",
            "vodforge_run_activity": ["Accepted", "Settled"],
        }
        history.save_history(ledger, app.download_history)

    app._archive_defer_history(kind, latest_callback, mutation=mutation)
    assert ArchiveLibraryMixin._archive_flush_history(app)
    restored = history.load_history(ledger)
    assert restored[0]["title"] == "Settled title"
    assert restored[0]["vodforge_run_activity"] == ["Accepted", "Settled"]


def test_unreadable_journal_stat_does_not_masquerade_as_absence(tmp_path, monkeypatch):
    ledger = tmp_path / "history.json"
    item = record(tmp_path / "clip.mp4")
    stage(ledger, item)
    journal = history.pending_history_path(ledger)
    accepted = journal.read_bytes()
    original = history.Path.stat

    def denied(path, *args, **kwargs):
        if path == journal:
            raise PermissionError("Injected inaccessible pending journal")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as injected:
        injected.setattr(history.Path, "stat", denied)
        with pytest.raises(history.HistoryError):
            stage(ledger, {**item, "title": "Do not overwrite"})
    assert journal.read_bytes() == accepted


@pytest.mark.parametrize(
    "mutation",
    [
        {"kind": "record", "record": {}},
        {"kind": "activity", "owners": [{}], "activity": []},
    ],
)
def test_invalid_staged_delta_preserves_previously_accepted_history(tmp_path, mutation):
    ledger = tmp_path / "history.json"
    stage(ledger, record(tmp_path / "clip.mp4"))
    journal = history.pending_history_path(ledger)
    accepted = journal.read_bytes()
    with pytest.raises(history.HistoryError):
        history.stage_history_mutation(ledger, mutation)
    assert journal.read_bytes() == accepted


@pytest.mark.parametrize("document", ["main", "pending"])
@pytest.mark.parametrize(
    "raw,cause",
    [
        ("{bad", "malformed_json"),
        ('{"schema_version":999}', "unsupported_schema"),
    ],
)
def test_history_failure_facts_preserve_document_and_explicit_cause(
    tmp_path, document, raw, cause
):
    path = tmp_path / "history.json"
    damaged = path if document == "main" else history.pending_history_path(path)
    damaged.write_text(raw)
    with pytest.raises(history.HistoryError) as caught:
        history.load_history(path)
    assert caught.value.document == document
    assert caught.value.cause == cause
    assert caught.value.phase == ("parse" if cause == "malformed_json" else "validate")
    assert damaged.read_text() == raw
