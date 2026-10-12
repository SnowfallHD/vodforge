"""Qt copy controls retain canonical ownership and private-content isolation."""

from __future__ import annotations

import json
from types import MethodType, SimpleNamespace

import pytest

from tests.test_product_telemetry import _permitted_installation
from yt_downloader.history import history_archive_owner
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.qt_quick.main import Bridge, QGuiApplication

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def copy_app(row, monkeypatch, telemetry=None):
    owner = history_archive_owner(row)
    copied = ["unchanged"]
    clipboard = SimpleNamespace(
        setText=lambda value: copied.__setitem__(slice(None), [value])
    )
    monkeypatch.setattr(QGuiApplication, "clipboard", lambda: clipboard)
    app = SimpleNamespace(
        _library_detail_owner=owner,
        _folder_inspector_owner="",
        _playback_record=None,
        _projected_library=lambda: [row],
        _saved_item_for_owner=lambda requested: row if requested == owner else None,
        statusChanged=SimpleNamespace(emit=lambda: None),
        _analytics=SimpleNamespace(telemetry=telemetry),
        copied=copied,
    )
    app._record_update_feature = MethodType(Bridge._record_update_feature, app)
    app.copyLibraryText = MethodType(Bridge.copyLibraryText, app)
    app.copySavedYoutubeUrl = MethodType(Bridge.copySavedYoutubeUrl, app)
    return app, owner


@pytest.mark.parametrize(
    "field,expected",
    [("source_tags", "provider"), ("source_description", "Source description")],
)
def test_source_copy_uses_canonical_metadata_not_personal_display(
    monkeypatch, field, expected
):
    app, owner = copy_app(
        {
            "tags": ["provider"],
            "description": "Source description",
            "vodforge_user_tags": ["PRIVATE"],
            "vodforge_user_note": "PRIVATE",
        },
        monkeypatch,
    )
    assert app.copyLibraryText(owner, field)
    assert app.copied == [expected]


@pytest.mark.parametrize(
    "field,expected",
    [
        ("source_tags", "provider, second"),
        ("source_description", "First line\nLast line"),
        ("tags", "PRIVATE, tag two"),
        ("note", "PRIVATE note\nsecond line"),
        ("thumbnail_url", "https://example.invalid/source.jpg"),
    ],
)
def test_copy_actions_honor_explicit_owner_snapshot(monkeypatch, field, expected):
    original = {
        "id": "original",
        "tags": ["provider", "second"],
        "description": "First line\nLast line",
        "vodforge_user_tags": ["PRIVATE", "tag two"],
        "vodforge_user_note": "PRIVATE note\nsecond line",
        "thumbnail": "https://example.invalid/source.jpg",
    }
    app, owner = copy_app(original, monkeypatch)
    unrelated = {"id": "other", "description": "Other owner"}
    app._projected_library = lambda: [unrelated, original]
    assert app.copyLibraryText(owner, field)
    assert app.copied == [expected]
    assert unrelated == {"id": "other", "description": "Other owner"}


@pytest.mark.parametrize(
    "field", ["source_tags", "source_description", "tags", "note", "thumbnail_url"]
)
def test_empty_owner_does_not_copy_display_placeholder_or_previous_owner(
    monkeypatch, field
):
    app, owner = copy_app({}, monkeypatch)
    assert not app.copyLibraryText(owner, field)
    assert not app.copyLibraryText("invalid", field)
    assert app.copied == ["unchanged"]


@pytest.mark.parametrize("consent", [False, True])
def test_actual_copy_controls_persist_only_bounded_telemetry(
    tmp_path, monkeypatch, consent
):
    installation = tmp_path / "installation.json"
    if consent:
        _permitted_installation(installation)
    monkeypatch.setattr(
        "yt_downloader.product_telemetry.telemetry_collection_allowed", lambda: True
    )
    telemetry = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _: False,
    )
    app, owner = copy_app(
        {
            "tags": ["PRIVATE source tag"],
            "description": "PRIVATE source description",
            "vodforge_user_tags": ["PRIVATE personal tag"],
            "vodforge_user_note": "PRIVATE note",
            "thumbnail": "https://example.invalid/PRIVATE.jpg",
            "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
        },
        monkeypatch,
        telemetry,
    )
    try:
        for field in (
            "source_tags",
            "source_description",
            "tags",
            "note",
            "thumbnail_url",
        ):
            assert app.copyLibraryText(owner, field)
        assert app.copySavedYoutubeUrl(owner)
    finally:
        telemetry.shutdown(2)
    events = [
        event.public_payload() for event in _load_outbox(tmp_path / "events.json")
    ]
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
