"""Readable bounded excerpts and a consented path to the original description."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_presentation_diagnostics import real_owner
from yt_downloader.archive_observations import usage
from yt_downloader.player_scene_ui import PlayerSceneMixin
from yt_downloader.product_telemetry import _load_outbox
from yt_downloader.ui_layout import ellipsize_wrapped_text, prose_excerpt

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize(
    "original,fitted,expected",
    [
        (
            "A journey through mountains",
            "A journey through moun\u2026",
            "A journey through\u2026",
        ),
        (
            "A journey through mountains",
            "A journey through\u2026",
            "A journey through\u2026",
        ),
        (
            "A quiet evening, with friends",
            "A quiet evening\u2026",
            "A quiet evening\u2026",
        ),
        (
            "Don't forget the forest",
            "Don't forget the for\u2026",
            "Don't forget the\u2026",
        ),
        (
            "First line\nSecond description continues",
            "First line\nSecond descrip\u2026",
            "First line\nSecond\u2026",
        ),
        ("Words with cafe\u0301 nearby", "Words with cafe\u2026", "Words with\u2026"),
        (
            "\u65e5\u672c\u8a9e\u306e\u6587\u7ae0",
            "\u65e5\u672c\u8a9e\u2026",
            "\u65e5\u672c\u8a9e\u2026",
        ),
        ("Unbrokenlongidentifier", "Unbrokenlong\u2026", "Unbrokenlong\u2026"),
        ("Complete sentence.", "Complete sentence.", "Complete sentence."),
        ("A pause\u2026", "A pause\u2026", "A pause\u2026"),
    ],
)
def test_excerpts_keep_word_boundaries_without_destroying_unspaced_text(
    original, fitted, expected
):
    assert prose_excerpt(original, fitted) == expected
    assert len(expected) <= len(fitted)


@pytest.mark.parametrize("width", [20, 35, 50])
def test_description_stays_inside_existing_measured_budget(width):
    original = "A peaceful journey across the mountains and forests with a winding river below."
    fitted = ellipsize_wrapped_text(
        original, maximum_width=width, maximum_lines=2, measure_width=len
    )
    excerpt = prose_excerpt(original, fitted)
    assert len(excerpt) <= len(fitted)
    if excerpt == original:
        return
    assert excerpt.endswith("\u2026")
    assert original.startswith(excerpt[:-1])
    assert (
        original[len(excerpt) - 1].isspace() or not original[len(excerpt) - 1].isalnum()
    )


def description_view(**kwargs):
    return SimpleNamespace(
        _closed=False,
        info={"description": "PRIVATE long description"},
        _description_expanded=False,
        _description_excerpt=Mock(),
        _description_more=Mock(),
        _description_panel=Mock(),
        _description_body=Mock(),
        _on_feature=Mock(),
        **kwargs,
    )


@pytest.mark.parametrize(
    "closed,has_text", [(False, True), (True, True), (False, False)]
)
def test_description_expands_in_place_and_ignores_retired_or_empty_players(
    closed, has_text
):
    view = description_view()
    view._closed = closed
    if not has_text:
        view.info["description"] = ""
    PlayerSceneMixin._read_description(view)
    if not closed and has_text:
        assert view._description_expanded
        view._description_panel.pack.assert_called_once_with(
            before=view._description_more, fill="x", pady=(8, 0)
        )
        view._description_more.configure.assert_called_once_with(text="Show less")
        PlayerSceneMixin._read_description(view)
        assert not view._description_expanded
        view._description_panel.pack_forget.assert_called_once()
        assert [c.args[0] for c in view._on_feature.call_args_list] == [
            "description_opened",
            "description_closed",
        ]
    else:
        view._description_panel.pack.assert_not_called()
        view._on_feature.assert_not_called()


@pytest.mark.parametrize("permission", ["allowed", "denied", "withdrawn"])
def test_read_more_actual_producer_respects_consent_and_contains_no_description(
    tmp_path, permission
):
    owner = real_owner(tmp_path, permitted=permission != "denied")
    if permission == "withdrawn":
        owner.set_enabled(False)
    view = description_view()
    view._on_feature = lambda action: usage(owner, "player", action)
    PlayerSceneMixin._read_description(view)
    PlayerSceneMixin._read_description(view)
    assert owner.shutdown(2)
    events = _load_outbox(tmp_path / "events.json")
    assert [e.action for e in events] == (
        ["description_opened", "description_closed"] if permission == "allowed" else []
    )
    assert "PRIVATE" not in repr([e.public_payload() for e in events])
