"""Archive additions to the cross-owner durable-effect and stale-result contract.

Uses production relink/history/worker owners and real fixture files. Existing
cross_owner_lifecycle tests exercise the same invariant for settings and transport.
"""

from __future__ import annotations

import json
import threading

import pytest

from tests.test_archive_relink import mapping, record
from tests.test_archive_work import wait_until
from yt_downloader.archive_relink import commit_relink, preview_relink, verify_relink
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.history import load_history, save_history


@pytest.mark.parametrize(
    "schedule", ["success", "cancel_before_effect", "stale_review", "failed_then_retry"]
)
def test_only_current_verified_intent_can_change_durable_history(
    tmp_path, monkeypatch, schedule
):
    new = tmp_path / "new"
    new.mkdir()
    media = new / "clip.mp4"
    media.write_bytes(b"untouched synthetic media")
    rows = [record(tmp_path / "old" / "clip.mp4")]
    ledger = tmp_path / "history.json"
    save_history(ledger, rows)
    before = ledger.read_bytes()
    media_before = media.read_bytes()
    preview = verify_relink(
        preview_relink(rows, [mapping(tmp_path / "old", new)]), rows
    )
    owner = ArchiveWorkOwner()
    entered, release = threading.Event(), threading.Event()
    commits = []

    def work(cancelled):
        entered.set()
        assert release.wait(2)
        updated = commit_relink(
            preview, rows, ledger, accepted=[0], cancelled=cancelled
        )
        commits.append(len(updated))
        return updated

    real_save = save_history
    if schedule == "failed_then_retry":

        def fail(*_args):
            raise OSError("injected durable write failure")

        monkeypatch.setattr("yt_downloader.history.save_history", fail)
    try:
        assert owner.submit("relink_apply", work) is not None
        assert entered.wait(2)
        if schedule == "cancel_before_effect":
            owner.cancel()
        elif schedule == "stale_review":
            rows[0]["title"] = "new authoritative title"
        release.set()
        results = []
        if schedule == "cancel_before_effect":
            wait_until(lambda: not owner.busy)
            assert owner.poll() is None
        else:
            wait_until(
                lambda: (
                    bool(results.append(value) or True)
                    if (value := owner.poll())
                    else False
                )
            )
        if schedule != "success":
            assert ledger.read_bytes() == before
            assert commits == []
        else:
            assert commits == [1] and not results[0].error
            assert load_history(ledger)[0]["vodforge_output_path"] == str(media)
        if schedule == "failed_then_retry":
            assert results[0].error == "OSError"
            monkeypatch.setattr("yt_downloader.history.save_history", real_save)
            assert owner.submit("relink_apply", work) is not None
            wait_until(
                lambda: (
                    bool(results.append(value) or True)
                    if (value := owner.poll())
                    else False
                )
            )
            assert not results[-1].error and commits == [1]
            assert json.loads(ledger.read_text())["items"][0][
                "vodforge_output_path"
            ] == str(media)
        assert media.read_bytes() == media_before
        assert not (tmp_path / "old").exists()
        assert not ledger.with_name(".history.json.tmp").exists()
    finally:
        release.set()
        owner.close()
        owner._thread.join(2)
        assert not owner._thread.is_alive()


@pytest.mark.parametrize("boundary", ["verify", "durable_save"])
@pytest.mark.parametrize("retire", ["cancel", "timeout", "close", "forced_close"])
def test_ui_transaction_keeps_actual_durable_outcome_and_flushes_deferred_writers(
    tmp_path, monkeypatch, boundary, retire
):
    from types import MethodType, SimpleNamespace

    import yt_downloader.archive_relink as relink
    from tests.test_archive_ui_owners import Variable
    from yt_downloader import history
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin

    new = tmp_path / "new"
    new.mkdir()
    target = new / "clip.mp4"
    target.write_bytes(b"synthetic-media")
    rows = [record(tmp_path / "old" / "clip.mp4")]
    ledger = tmp_path / "history.json"
    save_history(ledger, rows)
    preview = verify_relink(
        preview_relink(rows, [mapping(tmp_path / "old", new)]), rows
    )
    entered, release = threading.Event(), threading.Event()
    events, restored = [], []
    actual_verify, actual_save = relink.verify_relink, history.save_history

    if boundary == "verify":

        def blocked_verify(*args, **kwargs):
            entered.set()
            assert release.wait(3)
            return actual_verify(*args, **kwargs)

        monkeypatch.setattr(relink, "verify_relink", blocked_verify)
    else:

        def committed_but_not_returned(*args, **kwargs):
            actual_save(*args, **kwargs)
            entered.set()
            assert release.wait(3)

        monkeypatch.setattr(history, "save_history", committed_but_not_returned)

    worker = ArchiveWorkOwner()
    app = SimpleNamespace(
        _archive_worker=worker,
        _archive_commit_active=False,
        _archive_relink_operation="operation",
        download_history=rows,
        history_path=ledger,
        _closing=False,
        _archive_work_deadline=0,
        _archive_work_timeout=None,
        _archive_work_cancel=None,
        _archive_callback=None,
        status_var=Variable(),
        _archive_status=Variable(),
        product_telemetry=SimpleNamespace(
            record_operation=lambda feature, action, **kw: events.append(action)
        ),
        _event_write_diagnostic=lambda *args: None,
        _reconcile_library_projection=lambda: None,
        _archive_restore_browser=lambda: restored.append(True),
        after=lambda *args: "timer",
    )
    for name in [
        "_archive_submit",
        "_archive_usage",
        "_archive_observe",
        "_archive_apply_relink",
        "_archive_poll",
        "_archive_request_commit_cancel",
        "_archive_defer_history",
        "_archive_flush_history",
        "_archive_cancel_work",
        "_archive_destroyed",
    ]:
        setattr(app, name, MethodType(getattr(ArchiveLibraryMixin, name), app))
    control = SimpleNamespace(configure=lambda **kwargs: None)
    status = Variable()
    try:
        app._archive_apply_relink(preview, rows, (0,), status, control, control)
        assert entered.wait(2)
        other = record(tmp_path / "unrelated" / "other.mp4", identity="other")

        def deferred_write():
            app.download_history = [*app.download_history, other]
            actual_save(ledger, app.download_history)

        app._archive_defer_history(
            ("record", "other"),
            deferred_write,
            mutation={"kind": "record", "record": other},
        )
        if retire in {"close", "forced_close"}:
            app._closing = True
            app._archive_poll()
            if retire == "forced_close":
                from yt_downloader import app as application

                app.worker = None
                app._close_terminator = None
                app._close_deadline = 0.0
                app.after_cancel = lambda *args: None
                app.destroy = lambda: app._archive_destroyed(
                    SimpleNamespace(widget=app)
                )
                monkeypatch.setattr(
                    application,
                    "terminate_all_active_child_processes",
                    lambda **kwargs: None,
                )
                application.DownloaderApp._finish_application_close_when_idle(app)
        elif retire == "timeout":
            app._archive_work_deadline = 0.001
            app._archive_poll()
            assert "History is unchanged" not in status.value
        else:
            app._archive_request_commit_cancel()
        assert app._archive_commit_active
        assert (
            worker.submit("competing_write", lambda _: pytest.fail("Concurrent writer"))
            is None
        )
        release.set()
        if retire == "forced_close":
            worker._thread.join(3)
            assert not worker._thread.is_alive()
        else:
            wait_until(lambda: app._archive_poll() or not app._archive_commit_active)
        # Fresh process/load replays accepted deltas after a forced close.
        reloaded = load_history(ledger)
        assert len(reloaded) == 2 and {record["id"] for record in reloaded} == {
            "video",
            "other",
        }
        recovered = next(record for record in reloaded if record["id"] == "video")
        assert recovered["vodforge_output_path"] == (
            str(target)
            if boundary == "durable_save"
            else rows[0]["vodforge_output_path"]
        )
        assert events.count("committed") == (1 if boundary == "durable_save" else 0)
        if boundary == "verify":
            assert ("timed_out" if retire == "timeout" else "cancelled") in events
        else:
            assert not {"failed", "cancelled", "timed_out"}.intersection(events)
        assert not app.__dict__.get("_archive_deferred_history")
        assert restored == (
            [True]
            if boundary == "durable_save" and retire not in {"close", "forced_close"}
            else []
        )
        assert target.read_bytes() == b"synthetic-media"
    finally:
        release.set()
        worker.close()
        worker._thread.join(2)
        assert not worker._thread.is_alive()
