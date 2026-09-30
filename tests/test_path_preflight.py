"""New-output path checks happen after reuse and before staging or transfer."""

from types import SimpleNamespace

import pytest

from tests.test_metadata_helpers import (
    _worker_test_app,
    _worker_test_export_plan,
    _worker_test_job,
)
from yt_downloader import app


def units(path):
    return len(str(path).encode("utf-16-le")) // 2


def info():
    return {"id": "abc123", "title": "Video", "channel": "Creator"}


def test_exact_boundary_and_one_unit_over(monkeypatch, tmp_path):
    metadata = info()
    directory, filename = app.resolved_video_output_target(tmp_path, metadata, ".mp4")
    target = directory / filename
    monkeypatch.setattr(app, "WINDOWS_SAFE_PATH_LIMIT", units(target))
    assert app.preflight_video_output_target(tmp_path, metadata, ".mp4") == target
    monkeypatch.setattr(app, "WINDOWS_SAFE_PATH_LIMIT", units(target) - 1)
    compact = app.preflight_video_output_target(tmp_path, metadata, ".mp4")
    assert units(compact) < units(target)
    assert compact.is_relative_to(tmp_path)
    assert not tmp_path.joinpath("Creator").exists()


@pytest.mark.parametrize("extension", [".mp4", ".mp3", ".m4a", ".opus"])
def test_aggressive_shortening_preserves_hierarchy_and_metadata(tmp_path, extension):
    metadata = {
        "id": "abc123",
        "title": "🎬Full title" * 50,
        "channel": "Channel" * 40,
        "playlist_title": "Playlist" * 40,
    }
    original = dict(metadata)
    root = tmp_path / ("r" * max(1, 175 - units(tmp_path)))
    target = app.preflight_video_output_target(root, metadata, extension)
    assert units(target) <= app.WINDOWS_SAFE_PATH_LIMIT
    assert target.relative_to(root).parts[1] == "playlists"
    assert "[abc123]" in target.parent.name
    assert "path-safe videos" not in target.parts
    assert all(len(part.encode("utf-8")) <= 255 for part in target.parts)
    assert metadata == original
    assert not root.exists()


def test_irreducible_root_has_typed_choose_folder_contract(tmp_path):
    root = tmp_path / ("r" * 240)
    with pytest.raises(app.OutputPathBudgetError) as caught:
        app.preflight_video_output_target(root, info(), ".mp4")
    error = caught.value
    assert isinstance(error, ValueError)
    assert error.code == "output_path_too_long"
    assert error.action == "choose_output_folder"
    assert error.action_label == "Choose folder"
    assert str(error) == (
        "We can’t save your downloads in this folder because its full name is too long. "
        "Choose a different folder to continue."
    )
    assert not root.exists()


def test_collision_at_boundary_fits_and_preserves_existing_file(monkeypatch, tmp_path):
    metadata = info()
    directory, filename = app.resolved_video_output_target(tmp_path, metadata, ".mp4")
    first = directory / filename
    directory.mkdir(parents=True)
    first.write_bytes(b"existing")
    monkeypatch.setattr(app, "WINDOWS_SAFE_PATH_LIMIT", units(first))
    planned = app.preflight_video_output_target(tmp_path, metadata, ".mp4")
    assert planned != first
    assert planned.parent == first.parent
    assert planned.name.endswith(" (1).mp4")
    assert units(planned) <= units(first)
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"new")
    result = app.package_downloaded_media_from_staging(
        tmp_path, tmp_path, metadata, staged_media=[(metadata, staged)]
    )
    assert result == [planned]
    assert first.read_bytes() == b"existing"
    assert planned.read_bytes() == b"new"
    assert metadata["_vodforge_output_dir"] == str(planned.parent)


def test_collision_without_remaining_budget_is_rejected_before_creation(tmp_path):
    metadata = {"id": "x", "title": "V", "channel": "C"}
    directory, filename = app.resolved_video_output_target(tmp_path, metadata, ".mp4")
    root = tmp_path / ("r" * (240 - units(directory / filename) - 1))
    first = app.preflight_video_output_target(root, metadata, ".mp4")
    assert units(first) == app.WINDOWS_SAFE_PATH_LIMIT
    first.parent.mkdir(parents=True)
    first.write_bytes(b"keep")
    with pytest.raises(app.OutputPathBudgetError):
        app.preflight_video_output_target(root, metadata, ".mp4")
    assert first.read_bytes() == b"keep"
    assert list(root.rglob("*.mp4")) == [first]


def test_last_collision_suffix_fits_unicode_component_and_complete_path(tmp_path):
    metadata = {"id": "abc123", "title": "🎬" * 200, "channel": "C"}
    target = app._video_output_collision_target(tmp_path, metadata, ".mp4", 9999)
    assert target.name.endswith(" (9999).mp4")
    assert units(target) <= app.WINDOWS_SAFE_PATH_LIMIT
    assert len(target.name.encode("utf-8")) <= 255


def test_collision_lookup_is_bounded(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        app.os.path, "lexists", lambda candidate: calls.append(candidate) or True
    )
    with pytest.raises(RuntimeError, match="10,000 existing conflicts"):
        app.preflight_video_output_target(tmp_path, info(), ".mp4")
    assert len(calls) == 10_000
    assert calls[-1].name.endswith(" (9999).mp4")


@pytest.mark.parametrize("reuse", [False, True])
def test_worker_checks_after_reuse_before_expensive_work(monkeypatch, tmp_path, reuse):
    worker = _worker_test_app()
    root = tmp_path / ("r" * 240)
    job = _worker_test_job(root)
    metadata = info()
    analyzed = app._AnalyzedDownloadItem(
        preflight_info=metadata,
        display_info=metadata,
        plan=_worker_test_export_plan(),
        session_cookies=(),
        cookie_source_loaded=False,
    )
    order = []
    worker._analyze_download_item = lambda *_args, **_kwargs: (
        order.append("metadata") or analyzed
    )
    worker._try_reuse_existing_output = lambda *_args, **_kwargs: (
        order.append("reuse")
        or (
            app._ExistingOutputReuse(
                metadata=metadata, outcome=app.DownloadOutcome(success_count=1)
            )
            if reuse
            else None
        )
    )
    worker._complete_staged_download_item = lambda *_args: pytest.fail(
        "expensive staging/transfer reached"
    )
    worker._resolve_download_item_failure = lambda _job, _item, _result, error: error
    monkeypatch.setattr(
        app.DownloadWorkerCore,
        "_observe_download_operation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        app.DownloadWorkerCore, "_observed_intent_relation", lambda *_args: "unknown"
    )
    monkeypatch.setattr(
        app, "create_staging_dir", lambda *_args: pytest.fail("staging created")
    )
    source = app._DownloadSourceContext(
        ytdlp_module=object(),
        provider_network=SimpleNamespace(
            begin_primary=lambda *_args: order.append("lease"),
            end_primary=lambda: order.append("released"),
        ),
        playlist_info={},
        max_height=1080,
    )
    item = app._DownloadItemContext(
        entry=metadata, index=1, total=1, video_url=job.url, label="Video"
    )
    result = worker._coordinate_download_item(
        job, source, item, app._DownloadItemResult(outcome=app.DownloadOutcome())
    )
    assert order == ["lease", "metadata", "reuse", "released"]
    if reuse:
        assert result.outcome.success_count == 1
    else:
        assert isinstance(result, app.OutputPathBudgetError)
    assert not root.exists()
