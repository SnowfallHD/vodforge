"""Display original metadata separately from editable annotations."""

from copy import deepcopy

import pytest

from yt_downloader.library_scene_facts import library_detail_facts
from yt_downloader.library_text import library_copy_text, library_tag_values


@pytest.mark.parametrize(
    "source,user,combined",
    [
        (["Original"], [], "Original"),
        ([], ["Personal"], "Personal"),
        (["Original", "Shared"], ["shared", "Personal"], "Original, Shared, Personal"),
    ],
)
def test_combined_copy_is_deduplicated_without_mutating_either_tag_owner(
    source, user, combined
):
    row = {
        "tags": source,
        "vodforge_user_tags": user,
        "description": "Source description",
    }
    before = deepcopy(row)
    assert library_copy_text(row, "tags") == combined
    assert library_copy_text(row, "source_tags") == ", ".join(source)
    assert library_tag_values(row, "user_tags") == user
    assert library_copy_text(row, "note") == ""
    assert row == before


@pytest.mark.parametrize(
    "mode,rate,expected",
    [
        ("Everyday", "Quality", {"Preset": "Everyday", "Rate control": "Quality"}),
        ("Manual Override", "CBR", {"Preset": "Custom", "Rate control": "CBR"}),
        ("CBR", "CBR", {"Rate control": "CBR"}),
        ("Stream copy", "", {"Rate control": "Stream copy"}),
    ],
)
def test_output_details_label_preset_without_losing_distinct_rate_control(
    mode, rate, expected
):
    row = {
        "vodforge_output_dir": r"E:\Library\Video",
        "vodforge_output_path": r"E:\Library\Video\saved.mp4",
        "vodforge_encoding_summary": {
            "output": {
                "Output rate-control mode": mode,
                "Video rate control": rate,
                "Output file path": r"E:\Library\Video\saved.mp4",
            }
        },
    }
    before = deepcopy(row)
    _source, output = library_detail_facts(row)
    facts = {label: value for label, value, _icon in output}
    assert "File path" not in facts
    assert facts["Saved Filename"] == "saved.mp4"
    assert facts["Saved Location"] == r"E:\Library\Video"
    assert {key: facts[key] for key in expected} == expected
    if "Preset" not in expected:
        assert "Preset" not in facts
    assert row == before
