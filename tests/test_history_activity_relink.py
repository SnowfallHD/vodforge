from __future__ import annotations

from types import MethodType, SimpleNamespace

import pytest

from tests.test_archive_relink import mapping, record
from tests.test_archive_ui_owners import Variable
from yt_downloader import history
from yt_downloader.app import DownloaderApp
from yt_downloader.archive_library_ui import ArchiveLibraryMixin
from yt_downloader.archive_relink import (
    preview_relink,
    relocated_records,
    verify_relink,
)
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)


def job_for(path, item):
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=fixture",
        output_dir=path,
        output_type=OutputType.MP4,
        quality_label="1080p",
        export_mode=ExportMode.EVERYDAY,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=True,
        write_info_json=False,
        tags=[],
    )
    job.run_id = "run-one"
    job.history_identities = {history.history_identity(item)}
    job.activity_lines = ["Initial", "Accepted while relinking"]
    return job


@pytest.mark.parametrize("relocate", [False, True])
@pytest.mark.parametrize("phase", ["settlement", "after-settlement"])
def test_real_job_activity_survives_relink_without_updating_other_runs_or_variants(
    tmp_path, relocate, phase
):
    ledger = tmp_path / "history.json"
    old, new = tmp_path / "old", tmp_path / "new"
    new.mkdir()
    target = new / "clip.mp4"
    target.write_bytes(b"synthetic")
    item = record(old / "clip.mp4", run="run-one")
    item["vodforge_run_activity"] = ["Initial"]
    controls = [
        record(tmp_path / "foreign" / "clip.mp4", run="foreign-run"),
        record(tmp_path / "other-variant" / "clip.mp4", run="run-one"),
        {
            **record(tmp_path / "audio" / "clip.mp3", run="run-one"),
            "vodforge_output_type": "MP3",
        },
    ]
    for control in controls:
        control["vodforge_run_activity"] = ["Unrelated activity"]
    rows = [item, *controls]
    history.save_history(ledger, rows)
    job = job_for(old, item)
    app = SimpleNamespace(
        history_path=ledger,
        download_history=rows,
        _archive_commit_active=True,
        status_var=Variable(),
        _append_job_log=lambda *a: None,
        _reconcile_library_projection=lambda: None,
        _archive_usage=lambda *a, **k: None,
        _event_write_diagnostic=lambda *a: None,
    )
    for name in ["_archive_defer_history", "_archive_flush_history"]:
        setattr(app, name, MethodType(getattr(ArchiveLibraryMixin, name), app))
    app._persist_job_activity_to_history = MethodType(
        DownloaderApp._persist_job_activity_to_history, app
    )
    app._persist_job_activity_to_history(job)
    if relocate:
        preview = verify_relink(preview_relink(rows, [mapping(old, new)]), rows)
        history.save_history(ledger, relocated_records(preview, rows, accepted=[0]))
    app._archive_commit_active = False
    if phase == "settlement":
        job.activity_lines.append("Latest completion at settlement")
    assert app._archive_flush_history()
    if phase == "after-settlement":
        job.activity_lines.append("Latest completion after settlement")
        app._persist_job_activity_to_history(job)
    actual = history.load_history(ledger)
    assert len(actual) == 4
    selected = next(
        row
        for row in actual
        if row["vodforge_output_path"] == str(target if relocate else old / "clip.mp4")
    )
    assert selected["vodforge_run_activity"] == job.activity_lines
    for control in controls:
        restored = next(
            row
            for row in actual
            if history.history_identity(row) == history.history_identity(control)
        )
        assert restored["vodforge_run_activity"] == ["Unrelated activity"]
    assert target.read_bytes() == b"synthetic"
