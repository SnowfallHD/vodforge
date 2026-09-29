from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.test_archive_relink import record
from yt_downloader.archive_browser import (
    PAGE_SIZE,
    ArchiveBrowserModel,
    ArchiveComponent,
)
from yt_downloader.archive_paths import ArchivePath
from yt_downloader.history import history_archive_owner
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


def test_issues_only_include_terminal_runs_without_exports():
    rows = [
        {"id": "preview", "title": "Preview", "vodforge_preview_complete": True},
        {"id": "active", "title": "Active", "vodforge_run_status": "Downloading"},
        {"id": "queued", "title": "Queued", "vodforge_run_status": "Queued"},
        {
            "id": "retry-active",
            "title": "Retry active",
            "vodforge_run_status": "Downloading",
            "vodforge_issue_retry": True,
        },
        {
            "id": "retry-queued",
            "title": "Retry queued",
            "vodforge_run_status": "Queued",
            "vodforge_issue_retry": True,
        },
        *(
            {"id": status.lower(), "title": status, "vodforge_terminal_status": status}
            for status in ("Failed", "Stopped", "Skipped")
        ),
        saved("/archive/complete.mp4", video="complete"),
    ]
    model = ArchiveBrowserModel()
    model.replace(rows, range(len(rows)))
    model.navigate(None, mode="issues")
    assert model.mode_eligible_count == 5
    assert [component.title for component in model.components] == [
        "Retry active",
        "Retry queued",
        "Failed",
        "Stopped",
        "Skipped",
    ]
    model.navigate(None, mode="activity")
    assert [component.title for component in model.components] == [
        "Preview",
        "Active",
        "Queued",
        "Retry active",
        "Retry queued",
        "Failed",
        "Stopped",
        "Skipped",
    ]


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


def test_my_files_opens_single_saved_location_and_all_media_excludes_previews(tmp_path):
    from yt_downloader.archive_browser import ArchiveBrowserModel

    rows = [
        saved(tmp_path / "one" / "clip.mp4", video="one"),
        saved(tmp_path / "two" / "clip.mp4", video="two"),
        {"id": "preview", "title": "Preview"},
    ]
    model = ArchiveBrowserModel()
    model.replace(rows, [0, 1, 2])
    assert len(model.locations) == 1
    assert model.path == model.locations[0].path
    assert {item.title for item in model.components} == {"one", "two"}
    assert model.parent_path is None
    model.navigate(ArchivePath.parse(str(tmp_path / "one")))
    assert [str(path) for path in model.breadcrumbs] == [
        str(tmp_path),
        str(tmp_path / "one"),
    ]
    assert model.parent_path == ArchivePath.parse(str(tmp_path))
    model.navigate(None, mode="all")
    assert model.path is None
    assert [item.indices for item in model.components] == [(0,), (1,)]
    assert all(item.kind == "media" for item in model.components)
    model.replace(rows, [1, 2])
    assert [item.indices for item in model.components] == [(1,)]


def test_issues_include_only_observed_missing_saved_files_and_interrupted_runs():
    rows = [
        saved("/archive/one/ready.mp4", video="ready"),
        saved("/archive/two/missing.mp4", video="missing"),
        {"id": "stopped", "title": "Stopped", "vodforge_terminal_status": "Stopped"},
    ]
    model = ArchiveBrowserModel()
    model.replace(rows, range(len(rows)))
    model.navigate(None, mode="issues")
    assert [item.title for item in model.components] == ["Stopped"]
    missing_owner = history_archive_owner(rows[1])
    model.replace(rows, range(len(rows)), missing_owners=frozenset({missing_owner}))
    assert {(item.title, item.kind) for item in model.components} == {
        ("missing", "missing"),
        ("Stopped", "activity"),
    }


def test_my_files_uses_physical_entries_and_hides_missing_saved_file():
    rows = [
        saved("/archive/present.mp4", video="present"),
        saved("/archive/missing.mp4", video="missing"),
    ]
    model = ArchiveBrowserModel()
    model.replace(rows, range(len(rows)))
    model.navigate(ArchivePath.parse("/archive"))
    model.set_folder_entries(
        ArchivePath.parse("/archive"),
        [
            ArchiveComponent(
                "/archive/present.mp4",
                "file",
                "present.mp4",
                "Video",
                (),
                ArchivePath.parse("/archive/present.mp4"),
            ),
            ArchiveComponent(
                "/archive/thumbnail.jpg",
                "file",
                "thumbnail.jpg",
                "Image",
                (),
                ArchivePath.parse("/archive/thumbnail.jpg"),
            ),
        ],
    )
    assert [(item.title, item.kind) for item in model.components] == [
        ("present", "media"),
        ("thumbnail.jpg", "file"),
    ]
    assert model.unavailable_indices == (1,)


def test_my_files_identifies_missing_saved_child_folder_from_physical_listing():
    rows = [saved("/archive/Artist/album/track.mp4", video="track")]
    model = ArchiveBrowserModel()
    model.replace(rows, [0])
    parent = ArchivePath.parse("/archive/Artist")
    model.navigate(parent)
    model.set_folder_entries(parent, ())
    assert model.components == ()
    assert model.unavailable_indices == (0,)


def test_my_files_only_exposes_known_routes_until_a_media_folder():
    rows = [
        saved("/archive/Artist/song.mp4", video="song"),
        saved("/archive/Other/clip.mp4", video="clip"),
    ]
    model = ArchiveBrowserModel()
    model.replace(rows, range(len(rows)))
    root = ArchivePath.parse("/archive")
    model.navigate(root)
    model.set_folder_entries(
        root,
        [
            ArchiveComponent(
                str(root.join((name,))), "folder", name, "", (), root.join((name,))
            )
            for name in ("Artist", "Other", "Unrelated")
        ]
        + [
            ArchiveComponent(
                "/archive/notes.txt",
                "file",
                "notes.txt",
                "",
                (),
                ArchivePath.parse("/archive/notes.txt"),
            )
        ],
    )
    assert {item.title for item in model.components} == {"Artist", "Other"}

    artist = ArchivePath.parse("/archive/Artist")
    model.navigate(artist)
    model.set_folder_entries(
        artist,
        [
            ArchiveComponent(
                "/archive/Artist/song.mp4",
                "file",
                "song.mp4",
                "",
                (),
                ArchivePath.parse("/archive/Artist/song.mp4"),
            ),
            ArchiveComponent(
                "/archive/Artist/metadata.json",
                "file",
                "metadata.json",
                "",
                (),
                ArchivePath.parse("/archive/Artist/metadata.json"),
            ),
            ArchiveComponent(
                "/archive/Artist/extras",
                "folder",
                "extras",
                "",
                (),
                ArchivePath.parse("/archive/Artist/extras"),
            ),
        ],
    )
    assert {item.title for item in model.components} == {
        "song",
        "metadata.json",
        "extras",
    }
