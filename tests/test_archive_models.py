from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.test_archive_relink import record
from yt_downloader.archive_browser import PAGE_SIZE, ArchiveBrowserModel
from yt_downloader.archive_paths import ArchivePath
from yt_downloader.watch_library import watch_rails


def saved(
    path,
    *,
    video="one",
    playlist="list",
    channel="Creator",
    kind="MP4",
    provider="www.youtube.com",
):
    return {
        **record(path, identity=video),
        "title": video,
        "channel": channel,
        "webpage_url": f"https://{provider}/watch?v={video}",
        "playlist_id": playlist,
        "playlist_title": playlist,
        "vodforge_output_type": kind,
    }


def test_watch_downloaded_counts_are_videos_not_variants_or_remote_total():
    rows = [
        saved("/archive/one/a.mp4"),
        saved("/archive/two/a.mp3", kind="MP3"),
        saved("/archive/three/b.mp4", video="two"),
        {"id": "not-saved", "playlist_id": "list", "playlist_count": 999},
    ]
    rows[0]["playlist_count"] = 999
    rows[0]["playlist_index"] = 2
    rows[1]["playlist_index"] = 2
    rows[2]["playlist_index"] = 1
    before = copy.deepcopy(rows)
    (rail,) = watch_rails(rows)
    assert rail.downloaded_count == 2
    assert [video.title for video in rail.videos] == ["two", "one"]
    assert rail.videos[1].indices == (0, 1)
    assert rows == before


def test_watch_channels_contain_own_playlists_and_unlisted_saved_videos():
    rows = [
        saved("/a/a.mp4", playlist="Series", channel="Alpha"),
        saved("/b/b.mp4", playlist="Series", channel="Beta"),
        saved("/c/c.mp4", playlist="", channel="Alpha", video="standalone"),
    ]
    rails = watch_rails(rows, channel="Alpha")
    assert {rail.title for rail in rails} == {"Series", "Saved videos"}
    assert all(rail.channel == "Alpha" for rail in rails)
    assert all(len(rail.videos) == 1 for rail in rails)


def test_watch_collections_preserve_single_membership_and_provider_identity():
    rows = [
        saved("/a/a.mp4", provider="www.youtube.com"),
        saved("/b/a.mp4", provider="vimeo.com"),
        saved("/c/c.mp4", video="other"),
    ]
    rows[0]["vodforge_user_category"] = "Favorites"
    rows[1]["vodforge_user_category"] = "favorites"
    rows[2]["vodforge_user_category"] = "Elsewhere"
    rails = watch_rails(rows, collection_mode=True)
    shared = next(rail for rail in rails if rail.title.casefold() == "favorites")
    assert shared.downloaded_count == 2, "Different providers can reuse a source ID"
    assert sum(rail.downloaded_count for rail in rails) == 3


def test_archive_and_watch_projection_never_probe_offline_storage(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Browsing queried the filesystem")

    monkeypatch.setattr(Path, "stat", forbidden)
    rows = [saved(r"\\offline-nas\vault\series\clip.mp4")]
    model = ArchiveBrowserModel()
    model.replace(rows, [0])
    assert model.locations[0].path.style == "windows"
    model.navigate(None, mode="all")
    assert len(model.page_components) == 1
    assert watch_rails(rows)[0].downloaded_count == 1


def test_archive_selection_survives_reorder_and_reveal_respects_page_bound():
    rows = [saved(f"/a/{index}/clip.mp4", video=str(index)) for index in range(101)]
    model = ArchiveBrowserModel()
    model.replace(rows, range(len(rows)))
    model.navigate(None, mode="all")
    model.select(60)
    owner = model.selected_owner
    reordered = list(reversed(rows))
    model.replace(reordered, range(len(reordered)))
    assert model.selected_owner == owner
    assert model.selected_index() == 40
    assert len(model.page_components) == PAGE_SIZE
    model.reveal(40)
    assert model.selected_index() == 40
    assert any(40 in component.indices for component in model.page_components)
    assert len(model.page_components) <= PAGE_SIZE


def test_runs_and_previews_retain_authoritative_order_and_distinct_owners():
    rows = [
        {"id": "same", "title": "Zulu active", "vodforge_library_owner": "active:a"},
        {"id": "same", "title": "Alpha queued", "vodforge_library_owner": "queued:b"},
    ]
    from yt_downloader.library_state import PROJECTION_OWNER_KEY

    for index, row in enumerate(rows):
        row[PROJECTION_OWNER_KEY] = f"run:{index}"
    model = ArchiveBrowserModel()
    model.replace(rows, [0, 1])
    model.navigate(None, mode="activity")
    assert [component.indices for component in model.components] == [(0,), (1,)]


def test_archive_folder_mapping_uses_components_and_keeps_innermost_export():
    rows = [
        saved("/archive/Series/Export/a.mp4"),
        saved("/archive/Series-extra/Export/b.mp4", video="other"),
    ]
    model = ArchiveBrowserModel()
    model.replace(rows, [0, 1])
    model.navigate(ArchivePath.parse("/archive/Series"))
    assert [component.indices for component in model.components] == [(0,)]
    model.reveal(0)
    assert str(model.path) == "/archive/Series/Export"
