"""Requested-output identity must survive the filesystem ownership boundary."""

from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.app import package_downloaded_media_from_staging
from yt_downloader.models import Mp3ExportSettings, OutputType
from yt_downloader.run_identity import annotate_job_metadata


@pytest.mark.parametrize(
    "kind,extension",
    [
        (OutputType.MP4, ".mp4"),
        (OutputType.MP3, ".mp3"),
        (OutputType.ORIGINAL, ".opus"),
    ],
)
def test_different_settings_commit_to_separate_item_folders(tmp_path, kind, extension):
    job = replace(make_job(tmp_path), output_type=kind)
    variant = (
        replace(job, quality_label="720p HD")
        if kind is OutputType.MP4
        else (
            replace(job, mp3_settings=Mp3ExportSettings(bitrate_kbps=128))
            if kind is OutputType.MP3
            else replace(job, tags=["different"])
        )
    )
    outputs = []
    for index, intent in enumerate((job, variant)):
        staging = tmp_path / f"stage-{index}"
        staging.mkdir()
        source = staging / ("source" + extension)
        source.write_bytes(f"validated fixture {index}".encode())
        info = annotate_job_metadata(
            intent, {"id": "abc123", "title": "Same source", "channel": "QA"}
        )
        outputs.extend(
            package_downloaded_media_from_staging(
                staging,
                tmp_path,
                info,
                expected_extension=extension,
                staged_media=[(info, source)],
            )
        )
    assert outputs[0].parent != outputs[1].parent
    assert [path.read_bytes() for path in outputs] == [
        b"validated fixture 0",
        b"validated fixture 1",
    ]
    assert kind.value.split()[0].lower() in outputs[0].parent.name.lower()


def test_same_settings_keep_a_stable_folder_and_preserve_collision(tmp_path):
    job = make_job(tmp_path)
    outputs = []
    for index in range(2):
        staging = tmp_path / f"stage-{index}"
        staging.mkdir()
        source = staging / "source.mp4"
        source.write_bytes(str(index).encode())
        info = annotate_job_metadata(
            replace(job, run_id=str(index)), {"id": "abc123", "title": "Same source"}
        )
        outputs.extend(
            package_downloaded_media_from_staging(
                staging,
                tmp_path,
                info,
                expected_extension=".mp4",
                staged_media=[(info, source)],
            )
        )
    assert outputs[0].parent == outputs[1].parent
    assert outputs[0] != outputs[1]
    assert [path.read_bytes() for path in outputs] == [b"0", b"1"]


@pytest.mark.parametrize(
    "kind,extension",
    [
        (OutputType.ORIGINAL, ".m4a"),
        (OutputType.ORIGINAL, ".opus"),
    ],
)
def test_original_extensions_keep_the_same_requested_variant(tmp_path, kind, extension):
    job = replace(make_job(tmp_path), output_type=kind)
    info = annotate_job_metadata(job, {"id": "audio", "title": "Audio"})
    from yt_downloader.app import resolved_video_output_target

    directory, _ = resolved_video_output_target(tmp_path, info, extension)
    other, _ = resolved_video_output_target(
        tmp_path, info, ".opus" if extension == ".m4a" else ".m4a"
    )
    assert directory == other
    assert "Original audio" in directory.name


def test_variant_namespace_uses_effective_settings_not_only_display_label(tmp_path):
    from yt_downloader.run_identity import job_output_variant

    job = replace(make_job(tmp_path), output_type=OutputType.MP3)
    changed_channels = replace(
        job, mp3_settings=replace(job.mp3_settings, channels="1")
    )
    irrelevant_video_change = replace(job, quality_label="360p")
    assert job_output_variant(job) != job_output_variant(changed_channels)
    assert "mono" in job_output_variant(changed_channels)
    assert job_output_variant(job).startswith("MP3 320k")
    assert job_output_variant(job) == job_output_variant(irrelevant_video_change)


def test_shortened_paths_preserve_variant_and_item_identity(tmp_path):
    from yt_downloader.app import resolved_video_output_target
    from yt_downloader.run_identity import job_output_variant

    job = make_job(tmp_path)
    info = {
        "id": "abcdefghijk",
        "title": "Unicode title 😀 " * 15,
        "channel": "A very long channel " * 8,
    }
    first = annotate_job_metadata(job, info)
    second = annotate_job_metadata(replace(job, quality_label="720p HD"), info)
    paths = []
    for metadata in (first, second):
        directory, name = resolved_video_output_target(tmp_path, metadata, ".mp4")
        path = directory / name
        assert len(str(path).encode("utf-16-le")) // 2 <= 240
        assert "[abcdefghijk]" in directory.name
        paths.append(path)
    assert paths[0].parent != paths[1].parent
    assert job_output_variant(job)[-18:] in paths[0].parent.name


def test_provider_cannot_inject_variant_path(tmp_path):
    from yt_downloader.app import video_output_dir

    base = {"id": "abc", "title": "Video"}
    assert video_output_dir(
        tmp_path, {**base, "vodforge_output_variant": "../../escape"}
    ) == video_output_dir(tmp_path, base)


def test_parallel_variant_commits_do_not_mix_or_overwrite(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    job = make_job(tmp_path)

    def commit(index):
        intent = replace(job, quality_label="720p HD" if index else "1080p Full HD")
        staging = tmp_path / f"stage-{index}"
        staging.mkdir()
        media = staging / "source.mp4"
        media.write_bytes(f"independent-{index}".encode())
        info = annotate_job_metadata(intent, {"id": "same", "title": "Same"})
        return package_downloaded_media_from_staging(
            staging,
            tmp_path,
            info,
            staged_media=[(info, media)],
            expected_extension=".mp4",
        )[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(commit, (0, 1)))
    assert outputs[0].parent != outputs[1].parent
    assert [path.read_bytes() for path in outputs] == [
        b"independent-0",
        b"independent-1",
    ]


def test_legacy_reuse_is_bound_to_exact_saved_attempt_and_path(monkeypatch, tmp_path):
    import queue

    from yt_downloader import app as module
    from yt_downloader.export_planning import build_mp3_export_plan
    from yt_downloader.history import history_output_path, upsert_history

    job = replace(make_job(tmp_path), output_type=OutputType.MP3)
    metadata = {
        "id": "abc123",
        "title": "Legacy",
        "duration": 3,
        "formats": [
            {
                "format_id": "a",
                "vcodec": "none",
                "acodec": "opus",
                "abr": 128,
                "asr": 48000,
                "audio_channels": 2,
            }
        ],
    }
    plan = build_mp3_export_plan(metadata, job.mp3_settings)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    file = legacy / "original.mp3"
    file.write_bytes(b"legacy owned media")
    record = annotate_job_metadata(
        job,
        {
            **metadata,
            "vodforge_encoding_summary": {"output": {"Output file path": str(file)}},
        },
    )
    record.pop("vodforge_output_variant")
    history = upsert_history([], record, legacy)
    assert history_output_path(history[0]) == file
    app = module.DownloaderApp.__new__(module.DownloaderApp)
    app.events = queue.Queue()
    app.download_history = history
    app._find_ffprobe = lambda: "ffprobe"
    app._emit_job_log = lambda *_args: None
    monkeypatch.setattr(
        module, "save_cached_thumbnail_image", lambda *_args, **_kw: None
    )
    monkeypatch.setattr(module, "write_compact_video_metadata", lambda *_args: None)
    monkeypatch.setattr(
        module, "_validate_existing_output_candidate", lambda *_args, **_kw: {}
    )
    info = annotate_job_metadata(job, metadata)
    reused = app._try_reuse_existing_output(
        job, info, plan, label="legacy", all_output_dirs=[], control_check=lambda: None
    )
    assert reused is not None
    assert file.read_bytes() == b"legacy owned media"
    different = replace(job, mp3_settings=replace(job.mp3_settings, bitrate_kbps=128))
    assert (
        app._try_reuse_existing_output(
            different,
            annotate_job_metadata(different, metadata),
            plan,
            label="different",
            all_output_dirs=[],
            control_check=lambda: None,
        )
        is None
    )


def test_custom_variant_folders_show_the_changed_encoding_choice(tmp_path):
    from yt_downloader.models import ExportMode
    from yt_downloader.run_identity import job_output_variant

    job = replace(make_job(tmp_path), export_mode=ExportMode.MANUAL_OVERRIDE)
    crf18 = replace(job, manual_settings=replace(job.manual_settings, video_crf=18))
    crf23 = replace(job, manual_settings=replace(job.manual_settings, video_crf=23))
    assert "Custom CRF18" in job_output_variant(crf18)
    assert "Custom CRF23" in job_output_variant(crf23)


@pytest.mark.parametrize(
    "rate,channel,label",
    [
        ("48000", "2", "48kHz stereo"),
        ("44100", "1", "44_1kHz mono"),
        (None, None, "sourceHz sourceCh"),
    ],
)
def test_mp3_variant_label_accepts_saved_string_audio_choices(
    tmp_path, rate, channel, label
):
    from yt_downloader.run_identity import job_output_variant

    job = replace(
        make_job(tmp_path),
        output_type=OutputType.MP3,
        mp3_settings=Mp3ExportSettings(sample_rate=rate, channels=channel),
    )
    assert label in job_output_variant(job)


def test_observed_intent_relation_requires_actual_source_evidence(tmp_path):
    from types import SimpleNamespace

    from yt_downloader.app import DownloaderApp

    job = make_job(tmp_path)
    info = {"id": "abc123", "webpage_url": job.url}
    old = annotate_job_metadata(job, info)
    app = SimpleNamespace(download_history=[old])
    relation = DownloaderApp._observed_intent_relation
    assert relation(app, job, old) == "same_intent"
    changed = replace(job, quality_label="720p HD")
    assert (
        relation(app, changed, annotate_job_metadata(changed, info))
        == "different_settings"
    )
    different_source = {**old, "webpage_url": "https://example.com/unrelated"}
    assert relation(app, job, different_source) == "unknown"
    assert relation(app, job, {**old, "webpage_url": ""}) == "unknown"
    moved = replace(job, output_dir=tmp_path / "another")
    assert (
        relation(app, moved, annotate_job_metadata(moved, info))
        == "different_destination_or_organization"
    )


@pytest.mark.parametrize(
    "history",
    [
        None,
        {},
        "unavailable",
        [None],
        [42],
        [""],
        [{"id": []}],
        [{"id": "abc123", "webpage_url": []}],
        [{"id": "abc123", "vodforge_attempt_signature": {}}],
        [{"id": "abc123", "vodforge_output_variant": []}],
    ],
)
def test_intent_observation_malformed_evidence_is_unknown(tmp_path, history):
    from types import SimpleNamespace

    from yt_downloader.app import DownloaderApp

    job = make_job(tmp_path)
    info = annotate_job_metadata(job, {"id": "abc123", "webpage_url": job.url})
    assert (
        DownloaderApp._observed_intent_relation(
            SimpleNamespace(download_history=history), job, info
        )
        == "unknown"
    )


def test_intent_observation_distinguishes_absent_and_empty_history(tmp_path):
    from types import SimpleNamespace

    from yt_downloader.app import DownloaderApp

    job = make_job(tmp_path)
    info = {"id": "abc123", "webpage_url": job.url}
    assert (
        DownloaderApp._observed_intent_relation(SimpleNamespace(), job, info)
        == "unknown"
    )
    assert (
        DownloaderApp._observed_intent_relation(
            SimpleNamespace(download_history=[]), job, info
        )
        == "first_observed"
    )
