"""Presentation rename preserves actual converter profiles and saved records."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from yt_downloader.local_audio_video import (
    LocalVideoProfile,
    build_local_audio_video_command,
    new_local_audio_video_request,
)
from yt_downloader.local_video_labels import (
    local_video_profile_label,
    local_video_profile_text,
    local_video_profile_value,
)
from yt_downloader.run_identity import (
    metadata_output_profile,
    metadata_output_profile_details,
)


@pytest.mark.parametrize(
    "profile,label,digest",
    [
        (
            LocalVideoProfile.STANDARD,
            "Everyday",
            "c57dac6814ed354c9e14da9d6e590943695b962253ec79035cf3009b149ad8ce",
        ),
        (
            LocalVideoProfile.UHD,
            "4K",
            "bd0ee64b8c9a6a1d87cc31105d59b0e3a329936a28d16a28dc5e11be5bdecf72",
        ),
        (
            LocalVideoProfile.STRICT_CBR,
            "Broadcast",
            "c02ad663a28055795a7d1a0ac72b156e56b5d16ba3fff0c3320dc6e5067c9881",
        ),
        (
            LocalVideoProfile.COMPACT,
            "Smaller File",
            "07eb71614c95d44488823be4f6363bea4d11129f64b1c557aad686ff639a8081",
        ),
    ],
)
def test_display_selection_roundtrip_retains_pre_rename_full_ffmpeg_argv(
    profile, label, digest
):
    # Golden argv hashes captured from unchanged628 product before edits.
    assert local_video_profile_label(profile.value) == label
    assert local_video_profile_value(label) == profile.value
    for choice in (profile.value, label):
        request = new_local_audio_video_request(
            Path("input.mp3"), Path("still.png"), Path("."), profile=choice
        )
        assert request.profile is profile
        argv = build_local_audio_video_command(
            "ffmpeg",
            audio_path=Path("input.mp3"),
            image_path=Path("still.png"),
            output_path=Path("output.mp4"),
            profile=choice,
        )
        assert hashlib.sha256(json.dumps(argv).encode()).hexdigest() == digest


@pytest.mark.parametrize(
    "old,new",
    [
        ("1080p • Standard", "1080p • Everyday"),
        ("2160p • 4K", "2160p • 4K"),
        ("1080p • Strict 2 Mbps CBR", "1080p • Broadcast"),
        ("720p • Compact", "720p • Smaller File"),
    ],
)
def test_old_saved_profile_projects_new_label_without_rewriting_raw_metadata(old, new):
    info = {
        "vodforge_output_profile": f"MP4 • {old} • Static image",
        "vodforge_output_profile_details": f"MP4 • {old} • Static image\nOutput video codec: H.264\nOutput file path: /private/Standard.mp4",
    }
    before = copy.deepcopy(info)
    assert metadata_output_profile(info) == f"MP4 • {new} • Static image"
    assert (
        metadata_output_profile_details(info)
        == f"MP4 • {new} • Static image\nOutput video codec: H.264\nOutput file path: /private/Standard.mp4"
    )
    assert info == before


def test_activity_projection_changes_only_known_converter_generated_line():
    assert (
        local_video_profile_text(
            "Static-image MP4 encoded with 720p Compact and validated."
        )
        == "Static-image MP4 encoded with Smaller File and validated."
    )
    arbitrary = "User note: 720p Compact; committed /Standard.mp4"
    assert local_video_profile_text(arbitrary) == arbitrary
    assert local_video_profile_value("unknown") == "unknown"


def test_tk_display_choice_keeps_persisted_profile_variable():
    from yt_downloader.local_audio_video_ui import LocalAudioVideoDialog

    class Variable:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    dialog = LocalAudioVideoDialog.__new__(LocalAudioVideoDialog)
    dialog.profile_var = Variable(LocalVideoProfile.STANDARD.value)
    dialog.profile_display_var = Variable()
    dialog.profile_description_var = Variable()
    dialog._sync_profile_description()
    assert dialog.profile_display_var.get() == "Everyday"
    dialog.profile_display_var.set("Broadcast")
    dialog._select_profile_label()
    assert dialog.profile_var.get() == LocalVideoProfile.STRICT_CBR.value
    assert dialog.profile_display_var.get() == "Broadcast"
