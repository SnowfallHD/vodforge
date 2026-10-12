"""Observed outcomes must come from artifacts and never control their lifecycle."""

import json
import os
from pathlib import Path

import pytest

from yt_downloader import history as history_module
from yt_downloader.output_validation import observed_audio_characteristics


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
