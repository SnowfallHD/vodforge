from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.test_history_diagnostics import make_app, payloads
from yt_downloader.app import DownloaderApp

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def copy_app(rows):
    app = object.__new__(DownloaderApp)
    app.metadata_items = rows
    app.video_tree = SimpleNamespace(selection=lambda: ("0",))
    app.status_var = SimpleNamespace(set=lambda value: None)
    app.copied = ["unchanged"]
    app.clipboard_clear = lambda: app.copied.clear()
    app.clipboard_append = app.copied.append
    app.pulled_tags_text = SimpleNamespace(
        get=lambda *args: "Your tags: PRIVATE\nSource tags: provider"
    )
    app.description_text = SimpleNamespace(
        get=lambda *args: "YOUR NOTE\nPRIVATE\n\nSource description"
    )
    app.last_thumbnail_url = "https://example.invalid/previous-private.jpg"
    return app


@pytest.mark.parametrize(
    "method,expected",
    [
        ("_copy_tags", "provider"),
        ("_copy_description", "Source description"),
    ],
)
def test_source_copy_uses_canonical_metadata_not_personal_display(method, expected):
    app = copy_app(
        [
            {
                "tags": ["provider"],
                "description": "Source description",
                "vodforge_user_tags": ["PRIVATE"],
                "vodforge_user_note": "PRIVATE",
            }
        ]
    )
    assert getattr(app, method)()
    assert app.copied == [expected]


@pytest.mark.parametrize(
    "method,expected",
    [
        ("_copy_tags", "provider, second"),
        ("_copy_description", "First line\nLast line"),
        ("_copy_personal_tags", "PRIVATE, tag two"),
        ("_copy_personal_note", "PRIVATE note\nsecond line"),
        ("_copy_thumbnail_url", "https://example.invalid/source.jpg"),
    ],
)
def test_copy_actions_honor_explicit_owner_snapshot(method, expected):
    original = {
        "tags": ["provider", "second"],
        "description": "First line\nLast line",
        "vodforge_user_tags": ["PRIVATE", "tag two"],
        "vodforge_user_note": "PRIVATE note\nsecond line",
        "thumbnail": "https://example.invalid/source.jpg",
    }
    app = copy_app([{"description": "Other owner"}])
    assert getattr(app, method)(original)
    assert app.copied == [expected]
    assert app.metadata_items == [{"description": "Other owner"}]


@pytest.mark.parametrize(
    "method",
    [
        "_copy_tags",
        "_copy_description",
        "_copy_personal_tags",
        "_copy_personal_note",
        "_copy_thumbnail_url",
    ],
)
def test_empty_owner_does_not_copy_display_placeholder_or_previous_owner(method):
    app = copy_app([{}])
    assert not getattr(app, method)()
    assert app.copied == ["unchanged"]
    app.video_tree.selection = lambda: ("invalid",)
    assert not getattr(app, method)()
    assert app.copied == ["unchanged"]


@pytest.mark.parametrize("consent", [False, True])
def test_actual_copy_controls_persist_only_bounded_telemetry(
    tmp_path, monkeypatch, consent
):
    holder = make_app(tmp_path, monkeypatch, consent=consent)
    app = copy_app(
        [
            {
                "tags": ["PRIVATE source tag"],
                "description": "PRIVATE source description",
                "vodforge_user_tags": ["PRIVATE personal tag"],
                "vodforge_user_note": "PRIVATE note",
                "thumbnail": "https://example.invalid/PRIVATE.jpg",
                "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
            }
        ]
    )
    app.product_telemetry = holder.product_telemetry
    for method in (
        "_copy_tags",
        "_copy_description",
        "_copy_personal_tags",
        "_copy_personal_note",
        "_copy_thumbnail_url",
        "_copy_youtube_url",
    ):
        assert getattr(app, method)()
    events = payloads(holder)
    assert {event["action"] for event in events} == (
        {
            "source_tags_copied",
            "source_description_copied",
            "personal_tags_copied",
            "personal_note_copied",
            "thumbnail_url_copied",
            "youtube_url_copied",
        }
        if consent
        else set()
    )
    assert "PRIVATE" not in json.dumps(events)
