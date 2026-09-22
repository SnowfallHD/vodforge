"""Creator discovery uses the saved library, never invented recommendations."""

from yt_downloader.watch_library import watch_channels, watch_rails


def test_channel_counts_unique_saved_media_across_playlists_and_versions():
    records = [
        {
            "id": "one",
            "title": "One",
            "webpage_url": "https://example.test/one",
            "channel": "North",
            "playlist_id": playlist,
            "vodforge_output_dir": "/saved",
            "vodforge_output_type": output,
            "vodforge_user_category": "Travel",
        }
        for playlist, output in (("a", "MP4"), ("a", "MP3"), ("b", "MP4"))
    ]
    records.append(
        {
            "id": "two",
            "title": "Two",
            "webpage_url": "https://example.test/two",
            "channel": "North",
            "playlist_id": "b",
            "vodforge_output_dir": "/saved",
        }
    )
    records.append({"id": "preview", "title": "Preview", "channel": "Preview only"})
    channels = watch_channels(records)
    assert len(channels) == 1 and channels[0].name == "North"
    assert len(channels[0].videos) == 2
    assert watch_rails(records, collection_mode=True)[0].title == "Travel"
    assert watch_channels(records, query="missing") == ()


def test_unassigned_categories_and_empty_library_remain_empty():
    assert watch_channels([]) == ()
    assert (
        watch_rails(
            [{"id": "one", "vodforge_output_dir": "/saved"}], collection_mode=True
        )
        == ()
    )


def test_initial_category_mode_uses_saved_eligibility_and_preserves_choice():
    from types import SimpleNamespace

    from yt_downloader.watch_ui import WatchView

    state = SimpleNamespace(
        _records=(),
        _initial_mode_set=False,
        _mode="playlists",
        _artwork_attempted=set(),
        _queue_render=lambda: None,
        _presentation_change=lambda _trigger: None,
        _presentation_mode_counts={},
    )
    preview = {"id": "preview", "vodforge_user_category": "Travel"}
    saved = {"id": "saved", "vodforge_output_dir": "/saved"}
    WatchView.set_records(state, [preview])
    assert not state._initial_mode_set
    WatchView.set_records(state, [preview, saved])
    assert state._mode == "playlists" and state._initial_mode_set
    # Later projection changes retain the established or user-selected mode.
    WatchView.set_records(state, [{**saved, "vodforge_user_category": "Travel"}])
    assert state._mode == "playlists"
    state._initial_mode_set = False
    state._records = ()
    WatchView.set_records(state, [{**saved, "vodforge_user_category": "Travel"}])
    assert state._mode == "collections"


def test_stable_channel_membership_survives_rename_and_name_collisions():
    def row(video, name, channel, provider="youtube.com"):
        return {
            "id": video,
            "title": video,
            "channel": name,
            "channel_id": channel,
            "webpage_url": f"https://{provider}/watch?v={video}",
            "playlist_id": "shared-title",
            "vodforge_output_dir": "/saved",
        }

    records = [
        row("a", "Same name", "A"),
        row("b", "Same name", "B"),
        row("c", "Renamed", "A"),
        row("d", "Same name", "A", "vimeo.com"),
    ]
    channels = watch_channels(records)
    assert sorted(len(item.videos) for item in channels) == [1, 1, 2]
    combined = next(item for item in channels if len(item.videos) == 2)
    assert {
        v.title
        for rail in watch_rails(records, channel=combined.key)
        for v in rail.videos
    } == {"a", "c"}
    assert len({item.key for item in channels}) == 3
    assert len(watch_rails(records)) == 3


def test_channel_url_fallback_normalizes_host_without_fusing_distinct_paths():
    base = {"channel": "Creator", "vodforge_output_dir": "/saved"}
    rows = [
        {**base, "id": "a", "channel_url": "https://www.youtube.com/@alpha/"},
        {**base, "id": "b", "channel_url": "https://youtube.com/@alpha?ignored=1"},
        {**base, "id": "c", "channel_url": "https://youtube.com/@beta"},
    ]
    assert sorted(len(item.videos) for item in watch_channels(rows)) == [1, 2]
