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
