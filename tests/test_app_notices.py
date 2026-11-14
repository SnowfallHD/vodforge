"""Server notices: strict parsing, targeting and shown-once memory."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import pytest

from yt_downloader import app_notices as notices

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
VALID = {
    "id": "discord-open",
    "title": "Join the VODForge Discord",
    "body": "Ask questions and hear about updates first.",
    "link": {"label": "Join Discord", "url": "https://discord.gg/example"},
}


def parsed(*values):
    return notices.parse_notices({"version": 1, "notices": list(values)})


def test_a_complete_notice_parses():
    (notice,) = parsed(
        {
            **VALID,
            "platforms": ["windows"],
            "below_version": "0.3.0",
            "min_version": "0.2.8",
            "starts_at": "2026-11-01T00:00:00Z",
            "ends_at": "2026-12-01T00:00:00Z",
        }
    )
    assert notice.link_label == "Join Discord"
    assert notice.below_version == (0, 3, 0)
    assert notice.platforms == ("windows",)


@pytest.mark.parametrize(
    "change",
    [
        {"id": "Bad Id"},
        {"title": "x" * 81},
        {"body": ""},
        {"body": " padded"},
        {"link": {"label": "Open", "url": "http://example.com"}},
        {"link": {"label": "Open", "url": "https://user@example.com"}},
        {"link": {"label": "x" * 25, "url": "https://example.com"}},
        {"platforms": ["linux"]},
        {"platforms": []},
        {"below_version": "0.3"},
        {"starts_at": "2026-11-01T00:00:00"},
        {"starts_at": "2026-12-01T00:00:00Z", "ends_at": "2026-11-01T00:00:00Z"},
        {"color": "red"},
    ],
)
def test_any_invalid_part_skips_the_whole_notice(change):
    assert parsed({**VALID, **change}) == []


def test_wrong_version_or_shape_gives_nothing():
    assert notices.parse_notices({"version": 2, "notices": [VALID]}) == []
    assert notices.parse_notices([VALID]) == []
    assert notices.parse_notices({"version": 1, "notices": "x"}) == []


def test_duplicates_are_dropped_and_the_list_is_bounded():
    many = [VALID, VALID] + [
        {**VALID, "id": f"notice-{index:02d}"} for index in range(20)
    ]
    result = parsed(*many)
    assert len(result) == 9  # ten read, one duplicate
    assert result[0].id == "discord-open"


@pytest.mark.parametrize(
    ("change", "version", "platform", "shown"),
    [
        ({}, "0.2.8", "windows", True),
        ({"platforms": ["macos"]}, "0.2.8", "windows", False),
        ({"below_version": "0.2.8"}, "0.2.8", "windows", False),
        ({"below_version": "0.2.9"}, "0.2.8", "windows", True),
        ({"min_version": "0.2.9"}, "0.2.8", "windows", False),
        ({"min_version": "0.2.8"}, "0.2.8", "windows", True),
        ({"min_version": "0.2.8"}, "0.1.0-dev", "windows", False),
        ({"starts_at": "2026-11-16T00:00:00Z"}, "0.2.8", "windows", False),
        ({"ends_at": "2026-11-15T00:00:00Z"}, "0.2.8", "windows", False),
        ({"ends_at": "2026-11-16T00:00:00Z"}, "0.2.8", "windows", True),
    ],
)
def test_targeting(change, version, platform, shown):
    result = notices.next_notice(
        parsed({**VALID, **change}),
        version=version,
        platform=platform,
        seen=[],
        now=NOW,
    )
    assert (result is not None) is shown


def test_a_seen_notice_is_skipped_for_the_next_one():
    second = {**VALID, "id": "second-one"}
    result = notices.next_notice(
        parsed(VALID, second),
        version="0.2.8",
        platform="macos",
        seen=["discord-open"],
        now=NOW,
    )
    assert result is not None and result.id == "second-one"


def test_seen_memory_is_bounded_and_ignores_junk():
    seen = notices.remember_seen(["ok-one", 5, "Bad Id", "ok-one"], "new-one")
    assert seen == ["ok-one", "new-one"]
    many = [f"id-{index:03d}" for index in range(150)]
    assert len(notices.remember_seen(many, "last-one")) == notices.MAX_SEEN
    assert notices.remember_seen(None, "first-one") == ["first-one"]


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_fetch_sends_no_identifiers_and_reads_the_list():
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return _Response(json.dumps({"version": 1, "notices": [VALID]}).encode())

    (notice,) = notices.fetch_notices(opener=opener)
    assert notice.id == "discord-open"
    (request,) = requests
    assert request.full_url == "https://getvodforge.com/api/notices"
    assert request.get_method() == "GET"
    assert request.data is None
    assert {name.lower() for name, _ in request.header_items()} == {"accept"}


@pytest.mark.parametrize(
    "opener",
    [
        lambda request, timeout: (_ for _ in ()).throw(OSError("offline")),
        lambda request, timeout: _Response(b"not json"),
        lambda request, timeout: _Response(b"x" * (notices.MAX_RESPONSE_BYTES + 1)),
    ],
)
def test_fetch_failures_show_nothing(opener):
    assert notices.fetch_notices(opener=opener) == []
