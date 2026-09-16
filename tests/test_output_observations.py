"""Observed outcomes must come from artifacts and never control their lifecycle."""

import json
import os
import queue
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_state_authority import make_job
from yt_downloader import app as app_module
from yt_downloader import history as history_module
from yt_downloader.output_validation import observed_audio_characteristics


@pytest.mark.parametrize(
    "extension,codec", [(".mp4", "aac"), (".mp3", "mp3"), (".m4a", "aac")]
)
def test_download_commit_observation_precedes_metadata_projection_failure(
    tmp_path, monkeypatch, extension, codec
):
    job = make_job(tmp_path)
    job.telemetry_operation_id = str(uuid.uuid4())
    app = app_module.DownloaderApp.__new__(app_module.DownloaderApp)
    app.events = queue.Queue()
    app.download_history = []
    app._emit_job_log = lambda *_args: None
    observed = []
    app.product_telemetry = SimpleNamespace(
        permitted=lambda: True,
        record_operation=lambda *args, **kwargs: observed.append((args, kwargs)),
    )
    staged = tmp_path / ("staged" + extension)
    staged.write_bytes(b"validated-media-bytes")
    destination = tmp_path / "variant" / ("output" + extension)
    destination.parent.mkdir()

    def package(*_args, **_kwargs):
        staged.replace(destination)
        return [destination]

    def fail_projection(*_args, **_kwargs):
        raise ValueError("PRIVATE metadata projection failure")

    monkeypatch.setattr(app_module, "package_downloaded_media_from_staging", package)
    monkeypatch.setattr(app_module, "build_encoding_summary_metadata", fail_projection)
    probe = {
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": codec,
                "bit_rate": "192000",
                "sample_rate": "48000",
                "channels": 2,
            }
        ]
    }
    with pytest.raises(ValueError, match="metadata projection"):
        app._commit_validated_staged_media(
            job,
            {},
            None,
            tmp_path,
            extension,
            [({}, staged, probe)],
            label="QA",
            all_output_dirs=[],
            progress_callback=lambda _: None,
            control_check=lambda: None,
        )
    assert destination.read_bytes() == b"validated-media-bytes"
    assert len(observed) == 1
    assert observed[0][0] == ("download_operation", "committed")
    facts = observed[0][1]["dimensions"]
    assert facts["committed_count"] == "1"
    assert facts["observed_audio_codec"] == codec
    assert facts["observed_audio_bitrate_kbps"] == "192"
    assert facts["namespace_scan_state"] == "complete"
    assert facts["namespace_media_file_count"] == "1"


def audio_probe(codec="mp3", bitrate="128000", rate="44100", channels=2):
    return {
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": codec,
                "bit_rate": bitrate,
                "sample_rate": rate,
                "channels": channels,
            }
        ],
        "format": {"filename": "/PRIVATE/source.mp3", "tags": {"title": "PRIVATE"}},
    }


@pytest.mark.parametrize("codec", ["mp3", "aac", "opus", "flac"])
def test_audio_observations_use_only_probe_facts(codec):
    facts = observed_audio_characteristics(audio_probe(codec))
    assert facts == {
        "output_observation": "single",
        "observed_audio_state": "single",
        "observed_audio_codec": codec,
        "observed_audio_bitrate_kbps": "128",
        "observed_audio_sample_rate_hz": "44100",
        "observed_audio_channels": "2",
    }
    assert "PRIVATE" not in json.dumps(facts)


@pytest.mark.parametrize(
    "value", [True, False, 128.5, -1, 0, "N/A", "١٢٨", "9999999999", None]
)
def test_invalid_numeric_observations_are_absent(value):
    facts = observed_audio_characteristics(
        audio_probe(bitrate=value, rate=value, channels=value)
    )
    assert not any(
        key in facts
        for key in (
            "observed_audio_bitrate_kbps",
            "observed_audio_sample_rate_hz",
            "observed_audio_channels",
        )
    )


@pytest.mark.parametrize(
    "probe,state",
    [
        (None, "unknown"),
        ({}, "unknown"),
        ({"streams": [None]}, "unknown"),
        ({"streams": []}, "none"),
        ({"streams": [{"codec_type": "video"}]}, "none"),
        ({"streams": [{"codec_type": "audio"}, {"codec_type": "audio"}]}, "multiple"),
        ({"streams": [{}] * 65}, "unknown"),
    ],
)
def test_ambiguous_probe_never_invents_audio_properties(probe, state):
    facts = observed_audio_characteristics(probe)
    assert facts["observed_audio_state"] == state
    assert "observed_audio_codec" not in facts


@pytest.mark.parametrize(
    "count,state", [(0, "unavailable"), (2, "multiple"), (3, "multiple")]
)
def test_multiple_artifacts_do_not_claim_one_probe_describes_them(count, state):
    assert observed_audio_characteristics(audio_probe(), artifact_count=count) == {
        "output_observation": state,
        "observed_audio_state": "unknown",
    }


def make_output(tmp_path, directory, name="output.mp3"):
    p = tmp_path / directory / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"identical encoded media")
    return p


def source_info(signature="a"):
    return {
        "id": "source",
        "webpage_url": "https://example.test/media",
        "vodforge_attempt_signature": signature * 64,
    }


def history_record(path, signature="b"):
    return {
        **source_info(signature),
        "vodforge_output_dir": str(path.parent),
        "vodforge_output_path": str(path),
    }


def test_physical_namespace_distinction_does_not_depend_on_different_bytes(tmp_path):
    current = make_output(tmp_path, "variant-a")
    peer = make_output(tmp_path, "variant-b")
    assert current.read_bytes() == peer.read_bytes()
    facts = history_module.observed_output_namespace(
        current, source_info(), [history_record(peer)]
    )
    assert facts == {
        "namespace_scan_state": "complete",
        "namespace_media_file_count": "1",
        "peer_namespace_state": "distinct",
        "peer_comparison_count": "1",
    }
    assert str(tmp_path) not in json.dumps(facts)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("directory", "shared_directory"),
        ("artifact", "shared_artifact"),
    ],
)
def test_physical_collisions_are_observed(tmp_path, mode, expected):
    current = make_output(tmp_path, "variant-a")
    peer = tmp_path / ("variant-a" if mode == "directory" else "variant-b") / "peer.mp3"
    peer.parent.mkdir(exist_ok=True)
    if mode == "artifact":
        os.link(current, peer)
    else:
        peer.write_bytes(b"another file")
    facts = history_module.observed_output_namespace(
        current, source_info(), [history_record(peer)]
    )
    assert facts["peer_namespace_state"] == expected
    assert facts["peer_comparison_count"] == "1"


def test_reuse_same_intent_and_other_sources_are_not_compared(tmp_path):
    current = make_output(tmp_path, "variant-a")
    same = history_record(current, "a")
    other = {**history_record(current), "id": "unrelated"}
    url = {**history_record(current), "webpage_url": "https://example.test/other"}
    facts = history_module.observed_output_namespace(
        current, source_info(), [same, other, url]
    )
    assert facts["peer_namespace_state"] == "no_comparable"
    assert facts["peer_comparison_count"] == "0"


@pytest.mark.parametrize(
    "records,expected",
    [
        ([None], "unknown"),
        ([{"id": "source", "webpage_url": None}], "unknown"),
        ([{**source_info("b")}], "unknown"),
        (None, "unknown"),
        ([], "no_comparable"),
    ],
)
def test_incomplete_history_is_explicit(tmp_path, records, expected):
    current = make_output(tmp_path, "variant-a")
    assert (
        history_module.observed_output_namespace(current, source_info(), records)[
            "peer_namespace_state"
        ]
        == expected
    )


def test_missing_current_or_peer_is_explicit(tmp_path):
    current = make_output(tmp_path, "variant-a")
    missing = tmp_path / "missing" / "peer.mp3"
    facts = history_module.observed_output_namespace(
        current, source_info(), [history_record(missing)]
    )
    assert facts["peer_namespace_state"] == "missing"
    current.unlink()
    facts = history_module.observed_output_namespace(
        current, source_info(), [history_record(missing)]
    )
    assert facts["namespace_scan_state"] == "missing"
    assert "namespace_media_file_count" not in facts


def test_namespace_scan_is_shallow_and_capped(tmp_path):
    current = make_output(tmp_path, "variant-a")
    make_output(tmp_path, "variant-a/nested")
    (current.parent / "sidecar.json").write_text("{}")
    assert (
        history_module.observed_output_namespace(current)["namespace_media_file_count"]
        == "1"
    )
    for i in range(130):
        (current.parent / f"media-{i}.mp3").write_bytes(b"x")
    facts = history_module.observed_output_namespace(current)
    assert facts["namespace_scan_state"] == "capped"
    assert int(facts["namespace_media_file_count"]) <= 128


def test_peer_and_history_scans_have_separate_caps(tmp_path):
    current = make_output(tmp_path, "current")
    peers = [history_record(make_output(tmp_path, f"peer-{i}")) for i in range(33)]
    facts = history_module.observed_output_namespace(current, source_info(), peers)
    assert facts["peer_namespace_state"] == "capped"
    assert facts["peer_comparison_count"] == "32"
    facts = history_module.observed_output_namespace(
        current, source_info(), [{"id": "other"}] * 5001
    )
    assert facts["peer_namespace_state"] == "capped"
    assert facts["peer_comparison_count"] == "0"


def test_symlink_is_not_counted_as_regular_owned_media(tmp_path):
    current = make_output(tmp_path, "current")
    (current.parent / "linked.mp3").symlink_to(current)
    facts = history_module.observed_output_namespace(current)
    assert facts["namespace_scan_state"] == "unknown"
    assert facts["namespace_media_file_count"] == "1"


def test_filesystem_failure_is_unknown_or_unreadable_not_export_failure(
    tmp_path, monkeypatch
):
    current = make_output(tmp_path, "current")
    peer = make_output(tmp_path, "peer")

    def denied(*_args, **_kwargs):
        raise PermissionError("PRIVATE")

    monkeypatch.setattr(history_module.os, "scandir", denied)
    monkeypatch.setattr(Path, "samefile", denied)
    facts = history_module.observed_output_namespace(
        current, source_info(), [history_record(peer)]
    )
    assert facts["namespace_scan_state"] == "unreadable"
    assert facts["peer_namespace_state"] == "unreadable"
    assert "PRIVATE" not in json.dumps(facts)


@pytest.mark.parametrize("permission", [False, None, "error"])
def test_observation_io_requires_current_consent(tmp_path, monkeypatch, permission):
    app = app_module.DownloaderApp.__new__(app_module.DownloaderApp)

    def forbidden(*_args, **_kwargs):
        pytest.fail("No observation work may run while collection is unavailable")

    def denied():
        raise RuntimeError("PRIVATE")

    app.product_telemetry = SimpleNamespace(
        permitted=denied if permission == "error" else (lambda: permission)
    )
    monkeypatch.setattr(app_module, "observed_audio_characteristics", forbidden)
    monkeypatch.setattr(app_module, "observed_output_namespace", forbidden)
    assert (
        app._observed_output_dimensions(tmp_path / "missing.mp3", audio_probe()) == {}
    )


def test_enrichment_failures_preserve_core_commit_observation(tmp_path, monkeypatch):
    app = app_module.DownloaderApp.__new__(app_module.DownloaderApp)
    observed = []
    app.product_telemetry = SimpleNamespace(
        permitted=lambda: True,
        record_operation=lambda *args, **kwargs: observed.append((args, kwargs)),
    )
    job = make_job(tmp_path)
    job.telemetry_operation_id = str(uuid.uuid4())

    def fail(*_args, **_kwargs):
        raise ValueError("PRIVATE")

    monkeypatch.setattr(app_module, "observed_audio_characteristics", fail)
    monkeypatch.setattr(app_module, "observed_output_namespace", fail)
    app._observe_download_operation(
        job,
        "committed",
        stage="commit",
        dimensions={"committed_count": "1"},
        output_path=tmp_path / "file.mp3",
        output_probe=audio_probe(),
    )
    facts = observed[0][1]["dimensions"]
    assert facts["committed_count"] == "1"
    assert facts["observed_audio_state"] == "unknown"
    assert facts["namespace_scan_state"] == "unknown"
    assert "PRIVATE" not in json.dumps(facts)
    app.product_telemetry.record_operation = fail
    app._observe_download_operation(job, "committed", stage="commit")
    assert job.failure_stage == "commit"


def test_local_commit_observations_are_projected_without_exposing_probe(tmp_path):
    from yt_downloader.local_audio_video import LocalAudioVideoCommit

    app = app_module.DownloaderApp.__new__(app_module.DownloaderApp)
    observed = []
    app.product_telemetry = SimpleNamespace(
        permitted=lambda: True,
        record_operation=lambda *args, **kwargs: observed.append((args, kwargs)),
    )
    output = make_output(tmp_path, "local", "output.mp4")
    app._record_local_conversion_event(
        "local_conversion_committed",
        str(uuid.uuid4()),
        None,
        LocalAudioVideoCommit(output, audio_probe("aac", "191500", "48000", 1)),
    )
    facts = observed[0][1]["dimensions"]
    assert facts["committed_count"] == "1"
    assert facts["observed_audio_codec"] == "aac"
    assert facts["observed_audio_bitrate_kbps"] == "192"
    assert facts["observed_audio_sample_rate_hz"] == "48000"
    assert facts["observed_audio_channels"] == "1"
    assert facts["peer_namespace_state"] == "not_applicable"
    assert str(tmp_path) not in json.dumps(observed)
    assert "PRIVATE" not in json.dumps(observed)


@pytest.mark.parametrize(
    "extension,codec", [(".mp4", "aac"), (".mp3", "mp3"), (".opus", "opus")]
)
def test_reuse_observes_validated_artifact_before_metadata_projection(
    tmp_path, monkeypatch, extension, codec
):
    app = app_module.DownloaderApp.__new__(app_module.DownloaderApp)
    app._find_ffprobe = lambda: "trusted-probe"
    output = make_output(tmp_path, "retained", "output" + extension)
    app.download_history = []
    observations = []
    app.product_telemetry = SimpleNamespace(
        permitted=lambda: True,
        record_operation=lambda *args, **kwargs: observations.append((args, kwargs)),
    )
    job = make_job(tmp_path)
    job.telemetry_operation_id = str(uuid.uuid4())
    monkeypatch.setattr(
        app_module,
        "find_valid_existing_output",
        lambda *_args, **_kwargs: (output, audio_probe(codec)),
    )

    def fail_projection(*_args, **_kwargs):
        raise ValueError("PRIVATE")

    monkeypatch.setattr(app_module, "build_encoding_summary_metadata", fail_projection)
    with pytest.raises(ValueError):
        app._try_reuse_existing_output(
            job,
            source_info(),
            None,
            label="QA",
            all_output_dirs=[],
            control_check=lambda: None,
        )
    facts = observations[0][1]["dimensions"]
    assert observations[0][0] == ("download_operation", "reused")
    assert facts["committed_count"] == "0"
    assert facts["reused_count"] == "1"
    assert facts["observed_audio_codec"] == codec
    assert facts["observed_audio_bitrate_kbps"] == "128"
    assert output.read_bytes() == b"identical encoded media"


@pytest.mark.parametrize(
    "probe_available,expected",
    [(True, "no_eligible_candidate"), (False, "probe_unavailable")],
)
def test_reuse_miss_reason_comes_from_the_attempted_lookup(
    tmp_path, probe_available, expected
):
    app = app_module.DownloaderApp.__new__(app_module.DownloaderApp)
    app._find_ffprobe = lambda: "trusted-probe" if probe_available else None
    app.download_history = []
    observed = []
    app.product_telemetry = SimpleNamespace(
        permitted=lambda: True,
        record_operation=lambda *args, **kwargs: observed.append((args, kwargs)),
    )
    job = make_job(tmp_path)
    job.telemetry_operation_id = str(uuid.uuid4())
    assert (
        app._try_reuse_existing_output(
            job,
            source_info(),
            None,
            label="QA",
            all_output_dirs=[],
            control_check=lambda: None,
        )
        is None
    )
    facts = observed[0][1]["dimensions"]
    assert facts["stage"] == "reuse"
    assert facts["reuse_rejection"] == expected
    assert facts["reuse_result"] == ("miss" if probe_available else "unavailable")
