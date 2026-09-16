import io
import queue
import uuid
from dataclasses import replace

import pytest
from PIL import Image

from tests.test_product_telemetry import _permitted_installation
from tests.test_state_authority import make_job
from yt_downloader import app as app_module
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.fixture
def sidecar_case(tmp_path, monkeypatch):
    root = tmp_path / "exports"
    folder = root / "retained"
    folder.mkdir(parents=True)
    media = folder / "movie.mp4"
    media.write_bytes(b"unchanged independent media sentinel")
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    state = tmp_path / "events.json"
    owner = ProductTelemetryOwner(
        state_path=state,
        installation_state_path=installation,
        app_version="0.2.1",
        d1_recorder=lambda _event: False,
        heycatch_recorder=lambda *_args, **_kwargs: False,
    )
    app = app_module.DownloaderApp.__new__(app_module.DownloaderApp)
    app.product_telemetry = owner
    app.events = queue.Queue()
    app.download_history = []
    app._emit_job_log = lambda *_args: None
    app._find_ffprobe = lambda: "trusted-probe"
    info = {
        "id": "fixture",
        "title": "PRIVATE fixture",
        "webpage_url": "https://www.youtube.com/watch?v=fixture",
        "thumbnail": "https://i.ytimg.com/vi/fixture/hqdefault.jpg",
    }
    data = io.BytesIO()
    Image.new("RGB", (32, 24), (20, 40, 60)).save(data, "JPEG")
    cache = tmp_path / "cache" / "artwork.jpeg"
    monkeypatch.setattr(app_module, "cached_thumbnail_path", lambda *_a, **_k: cache)
    monkeypatch.setattr(
        app_module, "download_bounded_url_bytes", lambda *_a, **_k: data.getvalue()
    )
    monkeypatch.setattr(
        app_module, "resolved_video_output_dir", lambda *_a, **_k: folder
    )
    monkeypatch.setattr(
        app_module, "find_valid_existing_output", lambda *_a, **_k: (media, {})
    )
    monkeypatch.setattr(
        app_module,
        "build_encoding_summary_metadata",
        lambda metadata, *_a, **_k: metadata,
    )
    job = replace(make_job(root), write_info_json=True, write_thumbnail=True)
    job.telemetry_operation_id = str(uuid.uuid4())

    def run(reuse=False):
        if reuse:
            result = app._try_reuse_existing_output(
                job,
                info,
                None,
                label="QA",
                all_output_dirs=[],
                control_check=lambda: None,
            ).outcome
        else:
            result = app._record_committed_media_and_write_sidecars(
                job, info, media, label="QA", custom_cover_for_cache=None
            )
        assert owner.shutdown(2)
        assert media.read_bytes() == b"unchanged independent media sentinel"
        return result

    def facts():
        return [e for e in _load_outbox(state) if "sidecar_outcome" in e.dimensions]

    yield app, owner, job, info, folder, cache, run, facts
    assert owner.shutdown(2)


def test_sidecar_creation_and_rewrite_are_reported_at_real_write_boundaries(
    sidecar_case,
):
    _app, _owner, _job, info, folder, cache, run, facts = sidecar_case
    assert not run().sidecar_failure_count
    expected = {
        "metadata": "created",
        "thumbnail": "created",
        "library_artwork": "created",
    }
    assert {
        e.dimensions["sidecar_kind"]: e.dimensions["sidecar_outcome"] for e in facts()
    } == expected
    metadata = folder / app_module.safe_metadata_filename(info)
    assert metadata.is_file()
    for image_path in [folder / "thumbnail.jpeg", cache]:
        with Image.open(image_path) as image:
            image.load()
            assert image.size == (32, 24)
    assert not run().sidecar_failure_count
    after = facts()[3:]
    assert {
        e.dimensions["sidecar_kind"]: e.dimensions["sidecar_outcome"] for e in after
    } == {
        "metadata": "rewritten",
        "thumbnail": "rewritten",
        "library_artwork": "already_present",
    }
    assert all(e.dimensions["sidecar_context"] == "committed_media" for e in facts())
    assert "PRIVATE" not in str([e.public_payload() for e in facts()])


def test_missing_companions_repaired_on_reuse_without_media_changes(sidecar_case):
    _app, _owner, _job, info, folder, cache, run, facts = sidecar_case
    run()
    metadata = folder / app_module.safe_metadata_filename(info)
    prior = {
        p.name: p.read_bytes() for p in [metadata, folder / "thumbnail.jpeg", cache]
    }
    for path in [metadata, folder / "thumbnail.jpeg", cache]:
        path.unlink()
    assert not run(reuse=True).sidecar_failure_count
    restored = facts()[3:]
    assert len(restored) == 3
    assert all(e.dimensions["sidecar_outcome"] == "repaired" for e in restored)
    assert all(e.dimensions["sidecar_context"] == "reused_media" for e in restored)
    assert {
        p.name: p.read_bytes() for p in [metadata, folder / "thumbnail.jpeg", cache]
    } == prior


def test_disabled_and_unavailable_sidecars_are_distinct(sidecar_case):
    _app, _owner, job, info, folder, cache, run, facts = sidecar_case
    job.write_info_json = False
    job.write_thumbnail = False
    info.pop("thumbnail")
    run()
    assert {
        e.dimensions["sidecar_kind"]: e.dimensions["sidecar_outcome"] for e in facts()
    } == {
        "metadata": "not_requested",
        "thumbnail": "not_requested",
        "library_artwork": "unavailable",
    }
    assert not cache.exists()
    assert not (folder / "thumbnail.jpeg").exists()
    job.write_thumbnail = True
    run(reuse=True)
    assert {
        e.dimensions["sidecar_kind"]: e.dimensions["sidecar_outcome"]
        for e in facts()[3:]
    } == {
        "metadata": "not_requested",
        "thumbnail": "unavailable",
        "library_artwork": "unavailable",
    }


@pytest.mark.parametrize("reuse", [False, True])
def test_sidecar_failure_keeps_typed_detail_and_media_success(
    sidecar_case, monkeypatch, reuse
):
    _app, _owner, _job, _info, _folder, _cache, run, facts = sidecar_case

    def denied(*_args, **_kwargs):
        raise PermissionError(13, "PRIVATE path")

    monkeypatch.setattr(app_module, "write_compact_video_metadata", denied)
    outcome = run(reuse=reuse)
    assert outcome.sidecar_failure_count == 1
    assert outcome.failure_count == 0
    failed = [e for e in facts() if e.dimensions["sidecar_outcome"] == "failed"]
    assert len(failed) == 1
    assert failed[0].dimensions["sidecar_kind"] == "metadata"
    assert failed[0].failure_detail.stage == "sidecars"
    assert failed[0].dimensions["failed_count"] == "0"
    assert "PRIVATE" not in str(failed[0].public_payload())


def test_unusable_cache_repair_is_observed_from_real_validation(sidecar_case):
    _app, _owner, _job, _info, _folder, cache, run, facts = sidecar_case
    run()
    cache.write_bytes(b"invalid generated artwork")
    run()
    observed = [
        e for e in facts()[3:] if e.dimensions["sidecar_kind"] == "library_artwork"
    ]
    assert len(observed) == 1
    assert observed[0].dimensions["sidecar_outcome"] == "repaired"
    with Image.open(cache) as image:
        image.load()
        assert image.size == (32, 24)


def test_observer_failure_cannot_change_sidecar_writes(sidecar_case, monkeypatch):
    _app, owner, _job, info, folder, cache, run, facts = sidecar_case

    def failed_observer(*_args, **_kwargs):
        raise RuntimeError("PRIVATE diagnostic error")

    monkeypatch.setattr(owner, "record_operation", failed_observer)
    assert run().sidecar_failure_count == 0
    assert (folder / app_module.safe_metadata_filename(info)).is_file()
    assert (folder / "thumbnail.jpeg").is_file()
    assert cache.is_file()
    assert not facts()


def test_disabled_collection_does_not_inspect_sidecars_for_observations(
    sidecar_case, monkeypatch
):
    _app, owner, _job, _info, folder, cache, run, facts = sidecar_case
    owner.set_enabled(False)

    def forbidden(_path):
        pytest.fail("Disabled diagnostics attempted an extra filesystem observation")

    monkeypatch.setattr(app_module, "_sidecar_destination_state", forbidden)
    assert run().sidecar_failure_count == 0
    assert (folder / "thumbnail.jpeg").is_file()
    assert cache.is_file()
    assert not facts()


def test_unknown_prior_state_does_not_guess_creation(sidecar_case, monkeypatch):
    _app, _owner, _job, _info, _folder, _cache, run, facts = sidecar_case
    monkeypatch.setattr(app_module, "_sidecar_destination_state", lambda _path: None)
    assert run(reuse=True).sidecar_failure_count == 0
    assert len(facts()) == 3
    assert all(e.dimensions["sidecar_outcome"] == "unknown" for e in facts())


def test_unexpected_observation_error_is_unknown():
    class Unavailable:
        def lstat(self):
            raise ValueError("PRIVATE observation error")

    assert app_module._sidecar_destination_state(Unavailable()) is None


@pytest.mark.parametrize("helper", ["metadata", "thumbnail", "cache", "custom_cache"])
def test_write_helpers_isolate_callback_exceptions(tmp_path, monkeypatch, helper):
    info = {
        "id": "fixture",
        "title": "fixture",
        "thumbnail": "https://i.ytimg.com/vi/fixture/hqdefault.jpg",
    }
    data = io.BytesIO()
    Image.new("RGB", (32, 24), (20, 40, 60)).save(data, "JPEG")
    monkeypatch.setattr(
        app_module, "download_bounded_url_bytes", lambda *_a, **_k: data.getvalue()
    )
    monkeypatch.setattr(
        app_module, "cached_thumbnail_path", lambda *_a, **_k: tmp_path / "cache.jpeg"
    )

    def broken(_result):
        raise RuntimeError("PRIVATE observer error")

    if helper == "metadata":
        path = app_module.write_compact_video_metadata(
            tmp_path, info, [], on_result=broken
        )
    elif helper == "thumbnail":
        path = app_module.save_thumbnail_image(tmp_path, info, on_result=broken)
    elif helper == "cache":
        path = app_module.save_cached_thumbnail_image(info, on_result=broken)
    else:
        original = tmp_path / "original.jpg"
        original.write_bytes(data.getvalue())
        path = app_module.save_custom_cached_thumbnail_image(
            info, original, on_result=broken
        )
    assert path.is_file()
    if helper != "metadata":
        with Image.open(path) as image:
            image.load()
    assert not list(tmp_path.glob(".vfstage*"))


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("kind", ["metadata", "thumbnail"])
def test_real_companion_destination_conflict_has_typed_outbox_cause(
    sidecar_case, reuse, kind
):
    _app, _owner, _job, info, folder, _cache, run, facts = sidecar_case
    blocked = folder / (
        app_module.safe_metadata_filename(info)
        if kind == "metadata"
        else "thumbnail.jpeg"
    )
    blocked.mkdir()
    outcome = run(reuse=reuse)
    assert outcome.failure_count == 0
    assert outcome.sidecar_failure_count == 1
    assert blocked.is_dir() and not list(blocked.iterdir())
    failures = [e for e in facts() if e.dimensions["sidecar_outcome"] == "failed"]
    assert len(failures) == 1
    assert failures[0].dimensions["sidecar_kind"] == kind
    detail = failures[0].failure_detail.payload()
    assert detail["reason"] == "output_conflict"
    assert detail["error_type"] == "UnsafeOutputPathError"
    assert "os_error" not in detail
    assert "PRIVATE" not in str(failures[0].public_payload())
