from __future__ import annotations

from yt_downloader.library_search import (
    LIBRARY_ALL_MEDIA,
    library_search_terms,
    library_visible_indices,
)


def test_search_matches_user_and_provider_metadata_across_all_media() -> None:
    items = [
        {
            "title": "Deep work mix",
            "uploader": "Studio",
            "tags": ["ambient"],
            "vodforge_user_tags": ("Focus",),
            "vodforge_user_note": "Use on writing days",
            "vodforge_user_category": "Work",
            "vodforge_output_type": "MP4",
        },
        {
            "title": "Interview",
            "uploader": "Channel",
            "vodforge_user_category": "Research",
            "vodforge_output_type": "MP3",
        },
    ]

    assert library_visible_indices(items, LIBRARY_ALL_MEDIA, "writing focus") == [0]
    assert library_visible_indices(items, LIBRARY_ALL_MEDIA, "research") == [1]
    assert library_visible_indices(items, "MP4", "studio") == [0]
    assert library_visible_indices(items, "MP3", "studio") == []


def test_search_supports_quoted_phrases_and_is_order_stable() -> None:
    items = [
        {"title": "Alpha deep work", "vodforge_output_type": "MP4"},
        {"title": "Deep alpha work", "vodforge_output_type": "MP4"},
    ]

    assert library_search_terms('alpha "deep work"') == ("alpha", "deep work")
    assert library_visible_indices(items, "MP4", 'alpha "deep work"') == [0]
