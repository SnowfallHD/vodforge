from __future__ import annotations

from pathlib import Path

import pytest


def test_sandbox_initializes_persistent_diagnostics_before_resource_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from quality_harness.pipeline import configure_production_sandbox

    from yt_downloader import app

    monkeypatch.setattr(app, "DIAGNOSTICS_LOG_PATH", tmp_path / "latest.log")
    monkeypatch.setattr(app, "ACTIVITY_LOG_PATH", tmp_path / "activity.log")
    monkeypatch.setattr(app, "BATCH_FAILURE_REPORT_PATH", tmp_path / "failures.txt")
    monkeypatch.setattr(app, "_DIAGNOSTICS_LOG_HANDLE", None)
    monkeypatch.setattr(app, "_DIAGNOSTICS_LOG_HANDLE_PATH", None)
    try:
        configure_production_sandbox(tmp_path / "run")
        initial = app._DIAGNOSTICS_LOG_HANDLE
        assert initial is not None
        assert not initial.closed
        assert app._DIAGNOSTICS_LOG_HANDLE_PATH == app.DIAGNOSTICS_LOG_PATH
        for index in range(3):
            app.write_diagnostic(f"worker {index}")
            assert app._DIAGNOSTICS_LOG_HANDLE is initial
        initial.flush()
        assert "worker 2" in app.DIAGNOSTICS_LOG_PATH.read_text()
    finally:
        if app._DIAGNOSTICS_LOG_HANDLE is not None:
            app._DIAGNOSTICS_LOG_HANDLE.close()


def test_soak_contract_still_rejects_a_real_descriptor_increase() -> None:
    from quality_harness.release_gate import _deep_soak_contract

    metrics = {
        "jobs_attempted": 100,
        "jobs_completed": 100,
        "jobs_failed": 0,
        "worker_object_count_deltas": {
            "yt_dlp.YoutubeDL.YoutubeDL": 0,
            "yt_downloader.models.DownloadJob": 0,
        },
        "fd_delta": 0,
        "orphaned_child_processes": 0,
        "peak_zombie_processes": 0,
        "staging_residue_count": 0,
    }
    assert _deep_soak_contract({"metrics": metrics})["status"] == "passed"
    metrics["fd_delta"] = 1
    assert _deep_soak_contract({"metrics": metrics})["status"] == "failed"
