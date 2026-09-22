"""Protect the actual renderer's text allocations around trailing controls."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.library_detail_layout import LibraryDetailLayout
from yt_downloader.library_scene_facts import library_detail_facts


@pytest.mark.parametrize("width", [320, 360, 550, 720])
@pytest.mark.parametrize(
    "path",
    [
        "/Volumes/Media/" + "a very long media folder/" * 12,
        "C:\\" + "Very long translated folder name\\" * 12,
    ],
)
def test_actual_saved_path_allocation_stops_before_copy_target(width, path):
    texts = []
    buttons = []
    painter = SimpleNamespace(
        icon=lambda *_a, **_k: None,
        text=lambda x, y, value, **options: texts.append((x, y, value, options)),
        button=lambda x, y, w, label, callback, **options: buttons.append(
            (x, y, w, label, options)
        ),
    )
    state = SimpleNamespace(
        winfo_toplevel=lambda: SimpleNamespace(),
        _depth=Mock(),
        canvas=Mock(find_all=Mock(return_value=()), bbox=Mock(return_value=None)),
        _targets=[],
        _action=Mock(),
        _copy_value=Mock(),
    )
    LibraryDetailLayout._detail_panel(
        state,
        painter,
        31,
        50,
        width,
        "Output Details",
        "file",
        [("Saved Location", path, "folder")],
        0,
    )
    text = next(item for item in texts if item[2] == path)
    copy = next(item for item in buttons if item[4].get("icon") == "copy")
    assert text[3]["width"] > 0
    assert text[0] + text[3]["width"] <= copy[0] - 12
    assert state._targets[0][0][2] <= copy[0] - 12


def test_detail_facts_keep_actual_output_and_provider_values_separate():
    row = {
        "title": "Original title",
        "channel": "Source channel",
        "upload_date": "20260414",
        "vodforge_user_note": "My personal note",
        "vodforge_user_tags": ["Travel"],
        "vodforge_output_type": "MP4",
        "vodforge_output_path": "/saved/exact.mp4",
        "vodforge_output_dir": "/saved",
        "width": 3840,
        "height": 2160,
        "vodforge_encoding_summary": {
            "source": {"Source resolution": "3840x2160"},
            "output": {
                "Output resolution": "1920x1080",
                "Output video codec": "h264",
                "Output file size": "12 MB",
            },
        },
    }
    source, output = library_detail_facts(row)
    source = {label: value for label, value, _icon in source}
    output = {label: value for label, value, _icon in output}
    assert source["Original Title"] == "Original title"
    assert source["Source Resolution"] == "3840x2160"
    assert output["Output Resolution"] == "1920x1080"
    assert output["Saved Filename"] == "exact.mp4"
    assert source["Upload Date"] == "Apr 14, 2026"


def test_missing_facts_stay_unknown_instead_of_inventing_an_output():
    _source, output = library_detail_facts({"title": "Only metadata"})
    values = {label: value for label, value, _icon in output}
    assert values["Saved Filename"] == "Not recorded"
    assert values["Output Resolution"] == "Not recorded"
    assert values["File Size"] == "Not recorded"


@pytest.mark.parametrize("tags", [False, True])
@pytest.mark.parametrize("width", [320, 416, 694])
def test_detail_sections_use_inline_description_and_quiet_copy_without_manage(
    monkeypatch, tags, width
):
    import yt_downloader.scene_components as module

    texts = []
    canvas = Mock(find_all=Mock(return_value=()))
    canvas.create_text.side_effect = lambda *_args, **kwargs: (
        texts.append(kwargs["text"]) or len(texts)
    )
    monkeypatch.setattr(module.ImageTk, "PhotoImage", lambda *_a, **_k: object())
    state = SimpleNamespace(
        winfo_toplevel=lambda: SimpleNamespace(),
        canvas=canvas,
        _depth=Mock(),
        _surface=Mock(),
        _action=Mock(),
        _refresh_tag_hint=Mock(),
        _tag_entry=SimpleNamespace(winfo_reqheight=lambda: 28),
        _submit_tag=Mock(),
        _copy_value=Mock(),
        _description_section=SimpleNamespace(
            present=Mock(), height_for_width=lambda _: 180
        ),
        _targets=[],
        _button_images=[],
        _button_labels=[],
        _fit=lambda value, allocation, _lines, _font: (
            value if len(value) * 7 <= allocation else "..."
        ),
    )
    LibraryDetailLayout._detail_notes(
        state,
        module.ScenePainter(state),
        {},
        0,
        0,
        0,
        width,
        tags=tags,
    )
    assert "Manage" not in texts and "Add note" not in texts and "..." not in texts
    if not tags:
        state._description_section.present.assert_called_once()
        canvas.create_window.assert_called_once()
    else:
        assert "Tags" in texts


@pytest.mark.parametrize("width", [340, 620, 1116])
@pytest.mark.parametrize("count", [1, 2])
def test_sparse_library_collection_add_follows_actual_cards_without_phantom_slots(
    width, count
):
    from tests.test_scene_navigation import Painter, library_view

    view = library_view("home")
    view._records = view._records[:count]
    drawn = []
    view._collection_card = lambda _p, _g, _k, x, y, w: drawn.append((x, y, w))
    view._media_card = lambda *_args: None
    view._browse(Painter(view), width)
    add = next(
        box
        for box, callback in view._targets
        if getattr(callback, "func", None) == view._action
        and getattr(callback, "args", ()) == ("collection", None)
    )
    assert drawn
    previous_x, previous_y, card = drawn[-1]
    if previous_x + 2 * card + 14 <= width:
        assert add[0] == previous_x + card + 14
        assert add[1] == previous_y
    else:
        assert add[0] == 0 and add[1] > previous_y + 192
    assert add[2] <= width


def test_complete_source_output_comparison_preserves_measured_not_target_bitrates():
    from yt_downloader.encoding_summary import SUMMARY_COMPARISON_ROWS

    source_values = {
        source: "provider:" + source for _, source, _ in SUMMARY_COMPARISON_ROWS
    }
    output_values = {
        output: "measured:" + output
        for _, _, output in SUMMARY_COMPARISON_ROWS
        if output
    }
    source, output = library_detail_facts(
        {
            "vodforge_encoding_summary": {
                "source": source_values,
                "output": output_values,
            },
        }
    )
    source = {label: value for label, value, _ in source}
    output = {label: value for label, value, _ in output}
    assert source["Video bitrate"] == "provider:Source video bitrate"
    assert source["Audio bitrate"] == "provider:Source audio bitrate"
    assert output["Video bitrate"] == "measured:Measured video bitrate"
    assert output["Audio bitrate"] == "measured:Measured audio bitrate"
    assert set(source_values.values()) <= set(source.values())
    # Output container is presented as File Format.
    assert set(output_values.values()) <= set(output.values())


def test_target_bitrates_never_masquerade_as_measured_output_rates():
    _, output = library_detail_facts(
        {
            "vodforge_encoding_summary": {
                "source": {"Source video bitrate": "8000 kbps"},
                "output": {
                    "Target video bitrate": "4000 kbps",
                    "Target audio bitrate": "128 kbps",
                },
            }
        }
    )
    output = {label: value for label, value, _ in output}
    assert output["Video bitrate"] == output["Audio bitrate"] == "Not recorded"
    assert output["Target video bitrate"] == "4000 kbps"


@pytest.mark.parametrize(
    "kind", ["MP3", "M4A", "Original Audio", "Original audio", "Opus"]
)
def test_audio_facts_keep_audio_only_resolution_and_recorded_mp3_estimate(kind):
    source, output = library_detail_facts(
        {
            "vodforge_output_type": kind,
            "vodforge_encoding_summary": {
                "source": {"Effective MP3-equivalent audio bitrate": "192 kbps"},
                "output": {"Target audio bitrate": "256 kbps"},
            },
        }
    )
    source = {label: value for label, value, _ in source}
    output = {label: value for label, value, _ in output}
    assert output["Output Resolution"] == "Audio only"
    assert output["Audio bitrate"] == "Not recorded"
    if kind == "MP3":
        assert source["Effective audio bitrate"] == "192 kbps"
